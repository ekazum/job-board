"""Base class for careers sites too large to list, searched once per wanted role."""

from abc import ABC
from collections.abc import Sequence

from job_board.boards.board_source import BoardSource
from job_board.rules.keyword_filter import KeywordFilter
from job_board.rules.location_resolver import LocationResolver
from job_board.utils.http_client import HttpClient


class KeywordSearchSource(BoardSource, ABC):
    """A board read by searching it for each wanted role (the include keywords as plain text) instead of listing
    every job, keeping only titles that pass the role filter and jobs located in one of `locations`.

    Without a role filter the site is searched once with an empty query; without locations every location is kept.
    A job's location matches case-insensitively as a substring ("Israel" matches "Tel Aviv, Israel"), or, for a
    location that is a country, when it resolves to that country (LocationResolver: "United States" matches "US, CA").
    """

    def __init__(self, http: HttpClient, role_filter: KeywordFilter | None = None, locations: Sequence[str] = ()) -> None:
        super().__init__(http)
        self._role_filter = role_filter
        self._search_terms = (role_filter.search_terms if role_filter is not None else ()) or ("",)
        self._locations = tuple(location.strip() for location in locations if location.strip())
        codes = (LocationResolver.shared().country_code(location) for location in self._locations)
        self._countries = frozenset(code for code in codes if code is not None)

    def _wanted(self, title: str) -> bool:
        """The title passes the role filter (always, without one)."""
        return self._role_filter is None or self._role_filter.matches(title)

    def _in_location(self, text: str) -> bool:
        """True when no locations are configured, or the text names one of them or a place in one of their countries
        (for those that are countries)."""
        if not self._locations:
            return True
        lowered = text.lower()
        if any(location.lower() in lowered for location in self._locations):
            return True
        return not self._countries.isdisjoint(LocationResolver.shared().countries(text))
