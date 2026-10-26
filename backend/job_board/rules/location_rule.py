"""Which postings are in a place the candidate can work: the Profile's location, applied before scoring."""

from __future__ import annotations

import re

from job_board.models.profile import Profile
from job_board.rules.location_resolver import LocationResolver
from job_board.rules.place_names import PlaceNames

REASON_PREFIX = "location: "  # also matched in sql/postings/*.sql ('location: %')
NOT_GIVEN = "(not given)"
REMOTE = "remote"
FULLY_REMOTE_PHRASES = ("fully remote", "remote anywhere", "work from anywhere")
TITLE_BRACKETS = re.compile(r"[(\[]([^)\]]*)[)\]]")
TITLE_SEPARATORS = re.compile(r"\s+[-–—]\s+|[|,:/·•]")


class LocationRule:
    """The profile's location (a country or a city) and the posting's location are both resolved to countries
    (LocationResolver); a posting passes when they share one. With allow_fully_remote, a fully remote posting passes
    too: its location or title says remote without naming a place, or its description says "fully remote", "remote
    anywhere" or "work from anywhere" while its location names no place ("Remote - US" names one). When the posting's
    country is unknown (or the profile's), it passes only if its location, title or description contains the
    profile's location (spellings normalized). With no profile location set, nothing passes.

    A scanned job that fails is not stored; a stored posting that fails (after the location changed) is closed as
    not_relevant with fit_reason "location: <its location>", which puts it in the Archive (see ProfileSweep).
    """

    def __init__(self, location: str, allow_fully_remote: bool = False, resolver: LocationResolver | None = None) -> None:
        self._location = location.strip()
        self._place = PlaceNames.normalize(location)
        self._resolver = resolver or LocationResolver.shared()
        self._countries = self._resolver.countries(location) if self._place else ()
        self._allow_fully_remote = allow_fully_remote

    @classmethod
    def for_profile(cls, profile: Profile | None) -> LocationRule:
        """The rule the profile's location settings describe (a blank profile lets nothing pass)."""
        settings = profile or Profile()
        return cls(settings.location, settings.allow_fully_remote)

    @property
    def search_places(self) -> tuple[str, ...]:
        """Where the sites searched per role (Workday, Google, ...) look: the names of the profile location's countries
        ("Haifa" -> "Israel"), else the location as typed; () without a location, which searches everywhere."""
        names = tuple(name for name in map(self._resolver.country_name, self._countries) if name is not None)
        return names or ((self._location,) if self._location else ())

    def rejection(self, *, country: str | None, location: str, title: str, text: str) -> str | None:
        """None when the posting passes, else the fit_reason to store with it ("location: Paris, France"). country is
        the posting's resolved country, comma-separated when it has several (LocationResolver.resolve)."""
        if self._place and self._passes(country, location, title, text):
            return None
        return f"{REASON_PREFIX}{location.strip() or NOT_GIVEN}"

    @classmethod
    def is_remote(cls, *, location: str, title: str, text: str) -> bool:
        """The posting says it is remote: in its location or title, or as one of the fully-remote phrases."""
        return REMOTE in PlaceNames.normalize(location).split() or cls._title_remote_part(title) is not None or cls._says_fully_remote(text)

    @staticmethod
    def is_rejection(reason: str | None) -> bool:
        """Whether a fit_reason is one this rule wrote."""
        return reason is not None and reason.startswith(REASON_PREFIX)

    def _passes(self, country: str | None, location: str, title: str, text: str) -> bool:
        """Same country, or fully remote (when allowed), or, when a country is unknown, the profile's location named."""
        countries = {code for code in (country or "").split(",") if code}
        if countries.intersection(self._countries):
            return True
        if self._allow_fully_remote and self._fully_remote(location, title, text):
            return True
        if countries and self._countries:
            return False
        return self._place in PlaceNames.normalize(f"{location}\n{title}\n{text}")

    @classmethod
    def _fully_remote(cls, location: str, title: str, text: str) -> bool:
        """Remote, with no place named in the location or next to "remote" in the title."""
        title_part = cls._title_remote_part(title)
        if PlaceNames.place_words(location) or (title_part is not None and PlaceNames.place_words(title_part)):
            return False
        return REMOTE in PlaceNames.normalize(location).split() or title_part is not None or cls._says_fully_remote(text)

    @staticmethod
    def _title_remote_part(title: str) -> str | None:
        """The part of the title that says remote: the brackets around it ("(Remote - US)"), else everything from
        the separated piece with "remote" on ("AI Engineer - Remote, Europe" -> "Remote, Europe"); None without it."""
        for group in TITLE_BRACKETS.findall(title):
            if REMOTE in PlaceNames.normalize(group).split():
                return group
        pieces = TITLE_SEPARATORS.split(TITLE_BRACKETS.sub(" ", title))
        for index, piece in enumerate(pieces):
            if REMOTE in PlaceNames.normalize(piece).split():
                return " ".join(pieces[index:])
        return None

    @staticmethod
    def _says_fully_remote(text: str) -> bool:
        """The description uses one of the fully-remote phrases."""
        normalized = PlaceNames.normalize(text)
        return any(phrase in normalized for phrase in FULLY_REMOTE_PHRASES)
