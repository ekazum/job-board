"""Apple careers (jobs.apple.com), read through the search API its pages call."""

import asyncio
import logging
from urllib.parse import quote, urlencode

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.boards.keyword_search_source import KeywordSearchSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.json_values import as_dict, as_str, dicts

logger = logging.getLogger(__name__)

API_ROOT = "https://jobs.apple.com/api/v1"
JOB_URL = "https://jobs.apple.com/en-us/details/{}/{}"
LOCALE = "en-us"
PAGE_SIZE = 20
MAX_PAGES_PER_TERM = 25
DATE_FORMAT = {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}


class AppleSource(KeywordSearchSource):
    """Searches Apple's careers site once per wanted role, filtered to the configured locations.

    GET {API_ROOT}/refData/postlocation?input=Israel answers {"res": [{"id": "postLocation-ISR", "name": "Israel"}]},
    which turns each configured location into Apple's location ids. POST {API_ROOT}/search
    {"query": role, "filters": {"locations": ids}, "page": n, "locale": "en-us", ...} answers
    {"res": {"searchResults": [...], "totalRecords": n}}, 20 a page. A position open in several cities comes back
    once per city (id "200687183-1451", positionId "200687183"); those become one job. GET
    {API_ROOT}/jobDetails/{id}?locale=en-us answers {"res": {"description", "minimumQualifications", ...}}.
    The board's slug is "apple".
    """

    @property
    def platform(self) -> Platform:
        """Apple."""
        return Platform.APPLE

    @property
    def source(self) -> Source:
        """Apple."""
        return Source.APPLE

    async def probe(self, board: BoardRef) -> bool:
        """The search answers."""
        del board  # one site, whatever the slug
        return await self._search_page("", [], 1) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """One job per position found by any role search, in a configured location, with its description."""
        del board
        location_ids = await self._location_ids()
        if self._locations and not location_ids:
            logger.warning("apple: none of %s is an Apple job location", ", ".join(self._locations))
            return []
        per_term = await asyncio.gather(*(self._search_all(term, location_ids) for term in self._search_terms))
        if all(results is None for results in per_term):
            return None
        positions: dict[str, dict[str, dict[str, object]]] = {}  # positionId -> result id -> result
        for results in per_term:
            for result in results or []:
                position_id = as_str(result.get("positionId"))
                if position_id and self._wanted(as_str(result.get("postingTitle"))):
                    positions.setdefault(position_id, {}).setdefault(as_str(result.get("id")), result)
        grouped = ((position_id, list(by_id.values())) for position_id, by_id in positions.items())
        located = [(position_id, results) for position_id, results in grouped if self._in_location(self._location(results))]
        listings = await asyncio.gather(*(self._listing(position_id, results) for position_id, results in located))
        return [listing for listing in listings if listing is not None]

    async def _location_ids(self) -> list[str]:
        """Apple's ids for the configured locations ("Israel" -> "postLocation-ISR")."""
        ids: list[str] = []
        for location in self._locations:
            data = as_dict(await self._get_json(f"{API_ROOT}/refData/postlocation?{urlencode({'input': location})}"))
            for place in dicts((data or {}).get("res")):
                names = f"{as_str(place.get('name'))} {as_str(place.get('displayName'))}".lower()
                place_id = as_str(place.get("id"))
                if place_id and location.lower() in names and place_id not in ids:
                    ids.append(place_id)
        return ids

    async def _search_all(self, term: str, location_ids: list[str]) -> list[dict[str, object]] | None:
        """Every search result for one term, page by page; None when the search does not exist."""
        results: list[dict[str, object]] = []
        for page in range(1, MAX_PAGES_PER_TERM + 1):
            data = await self._search_page(term, location_ids, page)
            if data is None:
                return results or None  # a later page failing keeps what the first ones found
            batch = dicts(data.get("searchResults"))
            results.extend(batch)
            total = data.get("totalRecords")
            if not batch or not isinstance(total, int) or page * PAGE_SIZE >= total:
                break
        return results

    async def _search_page(self, term: str, location_ids: list[str], page: int) -> dict[str, object] | None:
        """The "res" object of one search page; None on 404."""
        filters: dict[str, object] = {"locations": location_ids} if location_ids else {}
        payload = {"query": term, "filters": filters, "page": page, "locale": LOCALE, "sort": "", "format": DATE_FORMAT}
        data = as_dict(await self._post_json(f"{API_ROOT}/search", payload))
        return None if data is None else as_dict(data.get("res"))

    async def _listing(self, position_id: str, results: list[dict[str, object]]) -> JobListing | None:
        """A position (all its cities) with the description of its first posting; None (logged) when that cannot be read."""
        first = results[0]
        job_id = as_str(first.get("id"))
        try:
            details = as_dict(await self._get_json(f"{API_ROOT}/jobDetails/{quote(job_id)}?locale={LOCALE}"))
        except BoardUnavailableError as error:
            logger.warning("apple: skipped %s, %s", job_id, error)
            return None
        info = as_dict((details or {}).get("res"))
        if info is None:
            return None
        sections = (
            as_str(info.get("jobSummary")),
            as_str(info.get("description")),
            self._section("Minimum qualifications", as_str(info.get("minimumQualifications"))),
            self._section("Preferred qualifications", as_str(info.get("preferredQualifications"))),
        )
        return JobListing(
            external_id=position_id,
            title=as_str(first.get("postingTitle")).strip(),
            url=JOB_URL.format(job_id, as_str(first.get("transformedPostingTitle"))),
            text="\n\n".join(section.strip() for section in sections if section.strip()),
            location=self._location(results),
        )

    @staticmethod
    def _location(results: list[dict[str, object]]) -> str:
        """Every city of a position's results as "Haifa, Israel | Herzliya, Israel"."""
        places = (
            ", ".join(part for part in (as_str(place.get("name")), as_str(place.get("countryName"))) if part)
            for result in results
            for place in dicts(result.get("locations"))
        )
        return " | ".join(dict.fromkeys(place for place in places if place))

    @staticmethod
    def _section(heading: str, body: str) -> str:
        """A titled block, or "" when there is no body."""
        return f"{heading}:\n{body.strip()}" if body.strip() else ""
