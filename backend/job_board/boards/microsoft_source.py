"""Microsoft careers (apply.careers.microsoft.com), read through the search API its pages call."""

import logging
from urllib.parse import urlencode

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.boards.keyword_search_source import KeywordSearchSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

logger = logging.getLogger(__name__)

API_ROOT = "https://apply.careers.microsoft.com/api/pcsx"
JOB_URL = "https://apply.careers.microsoft.com/careers/job/{}"
DOMAIN = "microsoft.com"
MAX_PAGES_PER_TERM = 20


class MicrosoftSource(KeywordSearchSource):
    """Searches Microsoft's careers site once per wanted role and configured location.

    GET {API_ROOT}/search?domain=microsoft.com&query=…&location=…&start=n answers
    {"data": {"positions": [...], "count": total}}, ten positions a page; a position has id, name and locations
    ("Israel, Tel Aviv, Herzliya"). GET {API_ROOT}/position_details?position_id=…&domain=microsoft.com&hl=en answers
    {"data": {"jobDescription": html, "publicUrl": …}}; 404 for an unknown position. Requests go one at a time:
    the API answers bursts with 429. The board's slug is "microsoft".
    """

    @property
    def platform(self) -> Platform:
        """Microsoft."""
        return Platform.MICROSOFT

    @property
    def source(self) -> Source:
        """Microsoft."""
        return Source.MICROSOFT

    async def probe(self, board: BoardRef) -> bool:
        """The search answers."""
        del board  # one site, whatever the slug
        return await self._search_page("", "", 0) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Jobs found by any role search, in a configured location, with descriptions; None if the API is gone."""
        del board
        positions: dict[str, dict[str, object]] = {}
        answered = False
        for term in self._search_terms:
            for location in self._locations or ("",):
                found = await self._search_all(term, location)
                answered = answered or found is not None
                for position in found or []:
                    position_id = as_id(position.get("id"))
                    title = as_str(position.get("name"))
                    if position_id and self._wanted(title) and self._in_location(self._places(position)):
                        positions.setdefault(position_id, position)
        if not answered:
            return None
        listings = [await self._listing(position_id, position) for position_id, position in positions.items()]
        return [listing for listing in listings if listing is not None]

    async def _search_all(self, term: str, location: str) -> list[dict[str, object]] | None:
        """Every position for one term and location, page by page; None when the API does not exist."""
        positions: list[dict[str, object]] = []
        for _ in range(MAX_PAGES_PER_TERM):
            data = await self._search_page(term, location, len(positions))
            if data is None:
                return positions or None  # a later page failing keeps what the first ones found
            batch = dicts(data.get("positions"))
            positions.extend(batch)
            count = data.get("count")
            if not batch or not isinstance(count, int) or len(positions) >= count:
                break
        return positions

    async def _search_page(self, term: str, location: str, start: int) -> dict[str, object] | None:
        """The data object of one search page; None on 404."""
        query = urlencode({"domain": DOMAIN, "query": term, "location": location, "start": start})
        return self._data(await self._get_json(f"{API_ROOT}/search?{query}"))

    async def _listing(self, position_id: str, position: dict[str, object]) -> JobListing | None:
        """A position with its description; None (logged) when its details cannot be read."""
        query = urlencode({"position_id": position_id, "domain": DOMAIN, "hl": "en"})
        try:
            details = self._data(await self._get_json(f"{API_ROOT}/position_details?{query}"))
        except BoardUnavailableError as error:
            logger.warning("microsoft: skipped position %s, %s", position_id, error)
            return None
        if details is None:
            return None
        return JobListing(
            external_id=position_id,
            title=as_str(position.get("name")).strip(),
            url=as_str(details.get("publicUrl")) or JOB_URL.format(position_id),
            text=HtmlTextParser.to_text(as_str(details.get("jobDescription"))),
            location=self._places(position),
        )

    @staticmethod
    def _places(position: dict[str, object]) -> str:
        """The position's locations, " | "-separated."""
        return " | ".join(as_str(place) for place in as_list(position.get("locations")) or [] if as_str(place))

    @staticmethod
    def _data(body: object) -> dict[str, object] | None:
        """The "data" object of an answer; None for a missing answer."""
        envelope = as_dict(body)
        return None if envelope is None else as_dict(envelope.get("data"))
