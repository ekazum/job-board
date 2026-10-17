"""Base class for careers sites too large to list, searched once per wanted role."""

from abc import ABC
from collections.abc import Sequence

from job_board.boards.board_source import BoardSource
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter


class KeywordSearchSource(BoardSource, ABC):
    """A board read by searching it for each wanted role (keywords.include as plain text) instead of listing every
    job, keeping only titles that pass the role filter and jobs located in one of `locations`.

    Without a role filter the site is searched once with an empty query; without locations every location is kept.
    Locations match case-insensitively as substrings ("Israel" matches "Tel Aviv, Israel").
    """

    def __init__(self, http: HttpClient, role_filter: KeywordFilter | None = None, locations: Sequence[str] = ()) -> None:
        super().__init__(http)
        self._role_filter = role_filter
        self._search_terms = (role_filter.search_terms if role_filter is not None else ()) or ("",)
        self._locations = tuple(location.strip() for location in locations if location.strip())

    def _wanted(self, title: str) -> bool:
        """The title passes the role filter (always, without one)."""
        return self._role_filter is None or self._role_filter.matches(title)

    def _in_location(self, text: str) -> bool:
        """True when no locations are configured or the text names one of them."""
        lowered = text.lower()
        return not self._locations or any(location.lower() in lowered for location in self._locations)
