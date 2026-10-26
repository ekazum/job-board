"""Turn a job's location text into ISO country codes, offline, from geonamescache's country and city lists."""

from __future__ import annotations

import re
from functools import cache

import geonamescache

from job_board.rules.place_names import PlaceNames

PLACE_SEPARATORS = re.compile(r"\s*(?:\||;|/|\n|\s+or\s+)\s*")  # places in one location: "Berlin / Tel Aviv", "A | B"
PART_SEPARATORS = re.compile(r",|\s[-–—]\s|[()]")  # parts of one place: "Tel Aviv, Israel", "Remote - US"
# Country names boards use besides geonamescache's own ("United States", "United Kingdom", "The Netherlands", ...).
COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "united states of america": "US",
    "uk": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "uae": "AE",
    "korea": "KR",
    "republic of korea": "KR",
    "czech republic": "CZ",
    "netherlands": "NL",
    "holland": "NL",
    "turkiye": "TR",
    "cote d ivoire": "CI",
    "palestine": "PS",
}


class LocationResolver:
    """Finds the countries a location names, as ISO 3166-1 alpha-2 codes:

    1. the board's own country field when it gives one (Comeet's location.country "IL", Workday's country): an
       alpha-2 or alpha-3 code or a country name;
    2. else, for each place in the text ("Berlin / Tel Aviv", "A | B", "A; B"), its comma- or dash-separated parts:
       the last part, then the first, as a country name ("Tel Aviv, Israel", "Israel, Raanana", "Remote - US");
    3. else the city, by its main name in geonamescache (the cities of 15,000 people or more), then by its other
       names, after normalizing spellings (PlaceNames: "Tel Aviv-Yafo", "Petach Tikva") and dropping trailing words
       ("Tel Aviv District"). A name used in several countries ("London") takes the one the place's other parts
       point to (a country code, or a US state: "San Francisco, CA"), else none.

    resolve() joins the codes found with commas, in order ("DE,IL"); None when there are none.
    """

    def __init__(self) -> None:
        data = geonamescache.GeonamesCache()
        countries = data.get_countries()
        self._alpha2 = frozenset(countries)
        self._alpha3 = {country["iso3"]: code for code, country in countries.items()}
        self._names = {code: country["name"] for code, country in countries.items()}
        self._country_names = {PlaceNames.normalize(country["name"]): code for code, country in countries.items()}
        self._country_names.update(COUNTRY_ALIASES)
        states = data.get_us_states()
        self._us_states = frozenset({code.lower() for code in states} | {PlaceNames.normalize(state["name"]) for state in states.values()})
        self._cities: dict[str, set[str]] = {}
        self._other_names: dict[str, set[str]] = {}
        for city in data.get_cities().values():
            self._cities.setdefault(PlaceNames.normalize(city["name"]), set()).add(city["countrycode"])
            for name in city["alternatenames"]:
                self._other_names.setdefault(PlaceNames.plain(name), set()).add(city["countrycode"])

    @staticmethod
    @cache
    def shared() -> LocationResolver:
        """One resolver for the process (building the city index takes about a second)."""
        return LocationResolver()

    def resolve(self, location: str, country_field: str = "") -> str | None:
        """The countries of a location ("IL", or "DE,IL" when it names places in both); None when unknown."""
        return ",".join(self.countries(location, country_field)) or None

    def countries(self, location: str, country_field: str = "") -> tuple[str, ...]:
        """The distinct countries of a location, in the order it names them."""
        own = self._field_country(country_field)
        if own is not None:
            return (own,)
        found: list[str] = []
        for place in PLACE_SEPARATORS.split(location):
            code = self._place_country(place)
            if code is not None and code not in found:
                found.append(code)
        return tuple(found)

    def country_code(self, name: str) -> str | None:
        """A country's alpha-2 code from its name or code ("Israel", "ISR", "IL" -> "IL"); None for anything else."""
        return self._field_country(name)

    def country_name(self, code: str) -> str | None:
        """The country's English name ("IL" -> "Israel"); None for an unknown code."""
        return self._names.get(code.upper())

    def _field_country(self, value: str) -> str | None:
        """A board's country field: "IL", "ISR" or "Israel"."""
        stripped = value.strip()
        if stripped.upper() in self._alpha2:
            return stripped.upper()
        return self._alpha3.get(stripped.upper()) or self._country_names.get(PlaceNames.normalize(stripped))

    def _place_country(self, place: str) -> str | None:
        """The country of one place: its last or first part as a country name, else its city."""
        parts = [words for words in (PlaceNames.place_words(part) for part in PART_SEPARATORS.split(place)) if words]
        if not parts:
            return None
        for part in (parts[-1], parts[0]):
            if part in self._country_names:
                return self._country_names[part]
        hints = {code for part in parts for code in self._hints(part)}
        for part in parts:
            candidates = self._city_countries(part)
            if len(candidates) == 1:
                return next(iter(candidates))
            if candidates:
                suggested = candidates & hints
                return next(iter(suggested)) if len(suggested) == 1 else None
        return None

    def _hints(self, part: str) -> set[str]:
        """Countries a part points to without naming a city: an alpha-2 code, a country name or a US state."""
        hints = {part.upper()} & self._alpha2
        if part in self._country_names:
            hints.add(self._country_names[part])
        if part in self._us_states:
            hints.add("US")
        return hints

    def _city_countries(self, part: str) -> set[str]:
        """The countries with a city of this name: main names first, then other names, dropping trailing words."""
        if len(part) <= 2:
            return set()
        words = part.split()
        for size in range(len(words), 0, -1):
            name = " ".join(words[:size])
            found = self._cities.get(name) or self._other_names.get(name)
            if found:
                return found
        return set()
