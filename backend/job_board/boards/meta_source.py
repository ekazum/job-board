"""Meta careers (metacareers.com), read through the GraphQL queries its search page runs."""

import asyncio
import json
import logging
import re
from collections.abc import Mapping

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.boards.keyword_search_source import KeywordSearchSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

logger = logging.getLogger(__name__)

SEARCH_PAGE = "https://www.metacareers.com/jobsearch/"
GRAPHQL_URL = "https://www.metacareers.com/graphql"
JOB_URL = "https://www.metacareers.com/jobs/{}/"
# Persisted query ids the search page sent on 2026-10-17; Meta replaces them when it redeploys the page.
SEARCH_QUERY = "27129360303422352"  # CareersJobSearchResultsV2DataQuery
OFFICES_QUERY = "24867916029505828"  # CareersJobSearchLocationFilterV3Query
LSD_TOKEN = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
JSON_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)


class MetaSource(KeywordSearchSource):
    """Searches Meta's careers site once per wanted role, in the offices of the configured locations.

    GET {SEARCH_PAGE} carries an anti-CSRF token ("LSD") that each POST {GRAPHQL_URL} repeats as the lsd form field
    and the x-fb-lsd header, next to doc_id (the persisted query) and variables. The offices query answers
    {"data": {"job_search_filters": {"locations": [{"location_display_name": "Tel Aviv, Israel", "country": ...}]}}};
    the configured locations pick the offices to search. The search query answers
    {"data": {"job_search_with_featured_jobs_v2": {"all_jobs": [{"id", "title", "locations"}]}}} with every match at
    once (its featured_jobs are promotions from anywhere and are ignored). A job's page embeds a schema.org JobPosting
    with the description, responsibilities and qualifications. The board's slug is "meta".
    """

    @property
    def platform(self) -> Platform:
        """Meta."""
        return Platform.META

    @property
    def source(self) -> Source:
        """Meta."""
        return Source.META

    async def probe(self, board: BoardRef) -> bool:
        """The search page has its token and the offices query answers."""
        del board  # one site, whatever the slug
        token = await self._token()
        return token is not None and await self._query(token, OFFICES_QUERY, {}) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Jobs found by any role search, in a configured location, with descriptions; None if the site is gone."""
        del board
        token = await self._token()
        if token is None:
            return None
        offices = await self._offices(token)
        if self._locations and not offices:
            logger.warning("meta: no office in %s", ", ".join(self._locations))
            return []
        per_term = await asyncio.gather(*(self._search(token, term, offices) for term in self._search_terms))
        found: dict[str, dict[str, object]] = {}
        for jobs in per_term:
            for job in jobs:
                job_id = as_id(job.get("id"))
                if job_id and self._wanted(as_str(job.get("title"))) and self._in_location(self._places(job)):
                    found.setdefault(job_id, job)
        listings = await asyncio.gather(*(self._listing(job_id, job) for job_id, job in found.items()))
        return [listing for listing in listings if listing is not None]

    async def _token(self) -> str | None:
        """The search page's LSD token; None when the page is gone, BoardUnavailableError when it has none."""
        page = await self._get(SEARCH_PAGE)
        if page is None:
            return None
        match = LSD_TOKEN.search(page.text)
        if match is None:
            raise BoardUnavailableError(f"meta {SEARCH_PAGE}: no LSD token on the page")
        return match.group(1)

    async def _offices(self, token: str) -> list[str]:
        """Names of the offices in a configured location ("Tel Aviv, Israel"); [] without configured locations."""
        if not self._locations:
            return []
        filters = as_dict((await self._query(token, OFFICES_QUERY, {}) or {}).get("job_search_filters")) or {}
        offices = (as_str(office.get("location_display_name")) for office in dicts(filters.get("locations")))
        return [office for office in offices if office and self._in_location(office)]

    async def _search(self, token: str, term: str, offices: list[str]) -> list[dict[str, object]]:
        """Every job matching one term in these offices."""
        search_input = {
            "q": term,
            "divisions": [],
            "offices": offices,
            "roles": [],
            "leadership_levels": [],
            "saved_jobs": [],
            "saved_searches": [],
            "sub_teams": [],
            "teams": [],
            "is_leadership": False,
            "is_remote_only": False,
            "sort_by_new": False,
            "results_per_page": None,
        }
        variables = {"search_input": search_input, "viewasUserID": None, "isLoggedIn": False}
        data = await self._query(token, SEARCH_QUERY, variables) or {}
        return dicts((as_dict(data.get("job_search_with_featured_jobs_v2")) or {}).get("all_jobs"))

    async def _query(self, token: str, doc_id: str, variables: Mapping[str, object]) -> dict[str, object] | None:
        """The "data" object of a GraphQL answer; None on 404, BoardUnavailableError when it reports errors."""
        fields = {"lsd": token, "doc_id": doc_id, "variables": json.dumps(variables)}
        response = await self._post_form(GRAPHQL_URL, fields, {"x-fb-lsd": token})
        if response is None:
            return None
        body = as_dict(self._parsed(GRAPHQL_URL, response.text)) or {}
        data = as_dict(body.get("data"))
        if data is None:
            errors = [as_str(error.get("message")) for error in dicts(body.get("errors"))]
            raise BoardUnavailableError(f"meta query {doc_id}: {'; '.join(errors) or 'no data'} (has the search page changed?)")
        return data

    async def _listing(self, job_id: str, job: dict[str, object]) -> JobListing | None:
        """A job with the description from its page; None (logged) when the page cannot be read."""
        url = JOB_URL.format(job_id)
        try:
            page = await self._get(url)
        except BoardUnavailableError as error:
            logger.warning("meta: skipped %s, %s", job_id, error)
            return None
        if page is None:
            return None
        posting = self._job_posting(page.text)
        sections = (as_str(posting.get(key)) for key in ("description", "responsibilities", "qualifications"))
        return JobListing(
            external_id=job_id,
            title=as_str(job.get("title")).strip(),
            url=url,
            text="\n\n".join(HtmlTextParser.to_text(section) for section in sections if section),
            location=self._places(job),
        )

    @staticmethod
    def _job_posting(html: str) -> dict[str, object]:
        """The page's schema.org JobPosting; {} when it has none."""
        for match in JSON_LD.finditer(html):
            try:
                data = as_dict(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue
            if data is not None and data.get("@type") == "JobPosting":
                return data
        return {}

    @staticmethod
    def _places(job: dict[str, object]) -> str:
        """The job's locations, " | "-separated."""
        return " | ".join(as_str(place) for place in as_list(job.get("locations")) or [] if as_str(place))
