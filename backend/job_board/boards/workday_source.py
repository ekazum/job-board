"""Workday job sites (<tenant>.<wd host>.myworkdayjobs.com/<site>)."""

import asyncio
import logging
import re
from collections.abc import Sequence

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_list, as_str, dicts

logger = logging.getLogger(__name__)

PAGE_SIZE = 20  # the jobs endpoint rejects a larger limit with 400
MAX_PAGES_PER_TERM = 50
MULTIPLE_LOCATIONS = re.compile(r"^\d+ Locations$")


class WorkdaySource(BoardSource):
    """Searches a Workday site once per wanted role and reads the description of each job that fits.

    POST {base}/wday/cxs/{tenant}/{site}/jobs {"appliedFacets": {}, "limit": 20, "offset": n, "searchText": role}
    pages through the search results; GET {base}/wday/cxs/{tenant}/{site}{externalPath} returns the job with its
    description. Searching (instead of listing a site's thousands of jobs) keeps a scan to the relevant jobs, and
    results whose title fails role_filter are dropped before their detail is fetched.

    locations, when given, keeps only jobs whose location contains one of them (case-insensitive). The listing's
    locationsText often reads "3 Locations", so those jobs are decided from the detail's location fields.
    external_id is the detail's jobPostingId, or the externalPath when it has none.
    """

    def __init__(self, http: HttpClient, role_filter: KeywordFilter | None = None, locations: Sequence[str] = ()) -> None:
        super().__init__(http)
        self._role_filter = role_filter
        self._search_terms = (role_filter.search_terms if role_filter is not None else ()) or ("",)
        self._locations = tuple(location.lower() for location in locations if location.strip())

    @property
    def platform(self) -> Platform:
        """Workday."""
        return Platform.WORKDAY

    @property
    def source(self) -> Source:
        """Workday."""
        return Source.WORKDAY

    async def probe(self, board: BoardRef) -> bool:
        """Board exists: the jobs endpoint answers with a jobPostings array."""
        return await self._search_page(board, "", 0, limit=1) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Matching jobs with descriptions; None when the site does not exist."""
        per_term = await asyncio.gather(*(self._search_all(board, term) for term in self._search_terms))
        if all(postings is None for postings in per_term):
            return None
        paths: dict[str, str] = {}
        for postings in per_term:
            for posting in postings or []:
                path = as_str(posting.get("externalPath"))
                title = as_str(posting.get("title"))
                if path and self._wanted(title) and self._may_be_in_location(as_str(posting.get("locationsText"))):
                    paths.setdefault(path, title)
        details = await asyncio.gather(*(self._listing(board, path, title) for path, title in paths.items()))
        return [listing for listing in details if listing is not None]

    async def _search_all(self, board: BoardRef, term: str) -> list[dict[str, object]] | None:
        """Every search result for one term, page by page; None when the site does not exist."""
        postings: list[dict[str, object]] = []
        for page in range(MAX_PAGES_PER_TERM):
            data = await self._search_page(board, term, page * PAGE_SIZE)
            if data is None:
                return None if page == 0 else postings
            batch = dicts(data.get("jobPostings"))
            postings.extend(batch)
            total = data.get("total")
            if not batch or not isinstance(total, int) or (page + 1) * PAGE_SIZE >= total:
                break
        return postings

    async def _search_page(self, board: BoardRef, term: str, offset: int, limit: int = PAGE_SIZE) -> dict[str, object] | None:
        """One page of search results, or None when the site does not exist (404)."""
        payload: dict[str, object] = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": term}
        data = as_dict(await self._post_json(f"{self._api_root(board)}/jobs", payload))
        if data is None or as_list(data.get("jobPostings")) is None:
            return None
        return data

    async def _listing(self, board: BoardRef, path: str, title: str) -> JobListing | None:
        """One job from its detail; None when it is outside the configured locations or cannot be read."""
        try:
            data = as_dict(await self._get_json(f"{self._api_root(board)}{path}"))
        except BoardUnavailableError as error:
            logger.warning("workday %s: skipped %s, %s", board.slug, path, error)
            return None
        info = as_dict((data or {}).get("jobPostingInfo"))
        if info is None:
            return None
        places = [as_str(info.get("location")), *(as_str(place) for place in as_list(info.get("additionalLocations")) or [])]
        if not self._in_location(" | ".join(places)):
            return None
        return JobListing(
            external_id=as_str(info.get("jobPostingId")) or path,
            title=as_str(info.get("title")).strip() or title,
            url=as_str(info.get("externalUrl")) or f"{self._site_root(board)}{path}",
            text=HtmlTextParser.to_text(as_str(info.get("jobDescription"))),
        )

    def _wanted(self, title: str) -> bool:
        """The listing title passes the role filter (always, without one)."""
        return self._role_filter is None or self._role_filter.matches(title)

    def _may_be_in_location(self, locations_text: str) -> bool:
        """Listing-level filter: definite matches and "N Locations" go on to the detail; others are dropped."""
        return MULTIPLE_LOCATIONS.match(locations_text) is not None or self._in_location(locations_text)

    def _in_location(self, text: str) -> bool:
        """True when no locations are configured or the text names one of them."""
        lowered = text.lower()
        return not self._locations or any(location in lowered for location in self._locations)

    @staticmethod
    def _api_root(board: BoardRef) -> str:
        """https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"""
        return f"https://{board.tenant}.{board.wd_host}.myworkdayjobs.com/wday/cxs/{board.tenant}/{board.site}"

    @staticmethod
    def _site_root(board: BoardRef) -> str:
        """https://{tenant}.{wd_host}.myworkdayjobs.com/{site}"""
        return f"https://{board.tenant}.{board.wd_host}.myworkdayjobs.com/{board.site}"
