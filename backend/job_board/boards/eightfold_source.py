"""Careers sites run on Eightfold (jobs.amdocs.com), read through the search API their pages call."""

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

MAX_PAGES_PER_TERM = 20


class EightfoldSource(KeywordSearchSource):
    """Searches an Eightfold careers site once per wanted role and configured location.

    GET https://{host}/api/pcsx/search?domain={domain}&query=…&location=…&start=n answers
    {"data": {"positions": [...], "count": total}}, ten positions a page; a position has id, name and locations
    ("Israel, Tel Aviv, Herzliya"). GET …/api/pcsx/position_details?position_id=…&domain={domain}&hl=en answers
    {"data": {"jobDescription": html, "publicUrl": …}}; 404 for an unknown position. Requests go one at a time:
    the API answers bursts with 429. The board's slug is the site's host and its tenant the domain the API asks for
    ("jobs.amdocs.com", "amdocs.com"; BoardLinkFinder reads both from the careers page).
    """

    @property
    def platform(self) -> Platform:
        """Eightfold."""
        return Platform.EIGHTFOLD

    @property
    def source(self) -> Source:
        """Eightfold."""
        return Source.EIGHTFOLD

    async def probe(self, board: BoardRef) -> bool:
        """The search answers."""
        return await self._search_page(board, "", "", 0) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Jobs found by any role search, in a configured location, with descriptions; None if the API is gone."""
        positions: dict[str, dict[str, object]] = {}
        answered = False
        for term in self._search_terms:
            for location in self._locations or ("",):
                found = await self._search_all(board, term, location)
                answered = answered or found is not None
                for position in found or []:
                    position_id = as_id(position.get("id"))
                    title = as_str(position.get("name"))
                    if position_id and self._wanted(title) and self._in_location(self._places(position)):
                        positions.setdefault(position_id, position)
        if not answered:
            return None
        listings = [await self._listing(board, position_id, position) for position_id, position in positions.items()]
        return [listing for listing in listings if listing is not None]

    def _api(self, board: BoardRef) -> tuple[str, str]:
        """The API root and the domain it asks for."""
        return f"https://{board.slug}/api/pcsx", board.tenant or ""

    def _job_url(self, board: BoardRef, position_id: str) -> str:
        """A position's page, for when its details name none."""
        return f"https://{board.slug}/careers/job/{position_id}"

    async def _search_all(self, board: BoardRef, term: str, location: str) -> list[dict[str, object]] | None:
        """Every position for one term and location, page by page; None when the API does not exist."""
        positions: list[dict[str, object]] = []
        for _ in range(MAX_PAGES_PER_TERM):
            data = await self._search_page(board, term, location, len(positions))
            if data is None:
                return positions or None  # a later page failing keeps what the first ones found
            batch = dicts(data.get("positions"))
            positions.extend(batch)
            count = data.get("count")
            if not batch or not isinstance(count, int) or len(positions) >= count:
                break
        return positions

    async def _search_page(self, board: BoardRef, term: str, location: str, start: int) -> dict[str, object] | None:
        """The data object of one search page; None on 404."""
        api, domain = self._api(board)
        query = urlencode({"domain": domain, "query": term, "location": location, "start": start})
        return self._data(await self._get_json(f"{api}/search?{query}"))

    async def _listing(self, board: BoardRef, position_id: str, position: dict[str, object]) -> JobListing | None:
        """A position with its description; None (logged) when its details cannot be read."""
        api, domain = self._api(board)
        query = urlencode({"position_id": position_id, "domain": domain, "hl": "en"})
        try:
            details = self._data(await self._get_json(f"{api}/position_details?{query}"))
        except BoardUnavailableError as error:
            logger.warning("%s: skipped position %s, %s", board.slug, position_id, error)
            return None
        if details is None:
            return None
        return JobListing(
            external_id=position_id,
            title=as_str(position.get("name")).strip(),
            url=as_str(details.get("publicUrl")) or self._job_url(board, position_id),
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
