"""Amazon careers (amazon.jobs), read through the search API its pages call."""

import asyncio
import json
from urllib.parse import urlencode

from job_board.boards.board_ref import BoardRef
from job_board.boards.job_listing import JobListing
from job_board.boards.keyword_search_source import KeywordSearchSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

SEARCH_URL = "https://www.amazon.jobs/en/search.json"
JOB_ROOT = "https://www.amazon.jobs"
PAGE_SIZE = 100
MAX_PAGES_PER_TERM = 10


class AmazonSource(KeywordSearchSource):
    """Searches amazon.jobs once per wanted role and configured location.

    GET {SEARCH_URL}?base_query=role&country=ISR&result_limit=100&offset=n answers {"hits": total, "jobs": [...]}
    with descriptions included. The search only narrows by country through its ISO-3 code; the free-text loc_query
    does not filter. So each configured location is first looked up as a search for its own name, and the ISO-3 codes
    of the jobs whose country is named like it ("Israel" -> ISR) are used. Each job's `locations` entries are JSON
    text with locationNonStemming ("Israel, Tel Aviv"), which also feeds the location filter. The board's slug is
    "amazon".
    """

    @property
    def platform(self) -> Platform:
        """Amazon."""
        return Platform.AMAZON

    @property
    def source(self) -> Source:
        """Amazon."""
        return Source.AMAZON

    async def probe(self, board: BoardRef) -> bool:
        """The search answers."""
        del board  # one site, whatever the slug
        return await self._search_page({"base_query": "", "result_limit": 1, "offset": 0}) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Jobs found by any role search, in a configured location, with descriptions; None if the search is gone."""
        del board
        countries = await self._country_codes()
        if self._locations and not countries:
            return []
        searches = [(term, country) for term in self._search_terms for country in countries or [""]]
        per_search = await asyncio.gather(*(self._search_all(term, country) for term, country in searches))
        if all(jobs is None for jobs in per_search):
            return None
        listings: dict[str, JobListing] = {}
        for jobs in per_search:
            for job in jobs or []:
                listing = self._listing(job)
                if listing is not None and self._wanted(listing.title) and self._in_location(listing.location):
                    listings.setdefault(listing.external_id, listing)
        return list(listings.values())

    async def _country_codes(self) -> list[str]:
        """ISO-3 codes of the configured locations, read from jobs found by searching for each location's name."""
        codes: list[str] = []
        for location in self._locations:
            found = await self._search_page({"base_query": location, "result_limit": PAGE_SIZE, "offset": 0}) or {}
            for job in dicts(found.get("jobs")):
                for place in (self._place(entry) for entry in as_list(job.get("locations")) or []):
                    code = as_str(place.get("countryIso3a"))
                    if code and location.lower() in as_str(place.get("normalizedCountryName")).lower() and code not in codes:
                        codes.append(code)
        return codes

    async def _search_all(self, term: str, country: str) -> list[dict[str, object]] | None:
        """Every job for one term in one country, page by page; None when the search does not exist."""
        jobs: list[dict[str, object]] = []
        for _ in range(MAX_PAGES_PER_TERM):
            params: dict[str, str | int] = {"base_query": term, "result_limit": PAGE_SIZE, "offset": len(jobs), "sort": "relevant"}
            data = await self._search_page({**params, "country": country} if country else params)
            if data is None:
                return jobs or None  # a later page failing keeps what the first ones found
            batch = dicts(data.get("jobs"))
            jobs.extend(batch)
            hits = data.get("hits")
            if not batch or not isinstance(hits, int) or len(jobs) >= hits:
                break
        return jobs

    async def _search_page(self, params: dict[str, str | int]) -> dict[str, object] | None:
        """One page of the search; None on 404."""
        return as_dict(await self._get_json(f"{SEARCH_URL}?{urlencode(params)}"))

    def _listing(self, job: dict[str, object]) -> JobListing | None:
        """One job; None without an id, title or link."""
        external_id = as_id(job.get("id_icims")) or as_id(job.get("id"))
        title = as_str(job.get("title")).strip()
        path = as_str(job.get("job_path"))
        if not (external_id and title and path):
            return None
        sections = (
            as_str(job.get("description")),
            self._section("Basic qualifications", as_str(job.get("basic_qualifications"))),
            self._section("Preferred qualifications", as_str(job.get("preferred_qualifications"))),
        )
        places = (as_str(self._place(entry).get("locationNonStemming")) for entry in as_list(job.get("locations")) or [])
        return JobListing(
            external_id=external_id,
            title=title,
            url=f"{JOB_ROOT}{path}",
            text="\n\n".join(HtmlTextParser.to_text(section) for section in sections if section),
            location=" | ".join(place for place in places if place) or as_str(job.get("normalized_location")),
        )

    @staticmethod
    def _place(entry: object) -> dict[str, object]:
        """A `locations` entry, which is JSON text; {} when it cannot be read."""
        if not isinstance(entry, str):
            return {}
        try:
            return as_dict(json.loads(entry)) or {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _section(heading: str, html: str) -> str:
        """A titled HTML block, or "" when there is no body."""
        return f"<p>{heading}:</p>{html}" if html.strip() else ""
