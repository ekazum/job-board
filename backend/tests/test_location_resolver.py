"""LocationResolver: a location string to ISO country codes, offline from geonamescache."""

import pytest

from job_board.location_resolver import LocationResolver


@pytest.fixture(scope="module")
def resolver() -> LocationResolver:
    return LocationResolver.shared()


@pytest.mark.parametrize(
    ("location", "country"),
    [
        ("Tel Aviv-Yafo", "IL"),
        ("Herzliya", "IL"),
        ("Petach Tikva", "IL"),
        ("Remote - US", "US"),
        ("Berlin / Tel Aviv", "DE,IL"),
        ("", None),
        ("Remote", None),
        ("Tel Aviv, Israel", "IL"),  # the last part as a country name
        ("Israel, Raanana | Israel, Yokneam", "IL"),  # Workday puts the country first
        ("IL, Tel Aviv", "IL"),  # a bare two-letter part is not taken as a country; the city decides
        ("Chicago, IL", "US"),  # ... so IL here stays Illinois
        ("Tel Aviv District", "IL"),  # trailing words are dropped until a city matches
        ("Haifa (remote)", "IL"),
        ("London, United Kingdom", "GB"),
        ("New York City, NY; San Francisco, CA | New York City, NY", "US"),
    ],
)
def test_locations_resolve_to_countries(resolver: LocationResolver, location: str, country: str | None) -> None:
    assert resolver.resolve(location) == country


def test_a_city_in_several_countries_takes_the_one_its_other_parts_suggest(resolver: LocationResolver) -> None:
    assert resolver.resolve("London") is None  # London, GB and London, Ontario
    assert resolver.resolve("San Francisco") is None  # also in Argentina, the Philippines, ...
    assert resolver.resolve("San Francisco, CA") == "US"  # CA as a US state


def test_the_boards_own_country_field_comes_first(resolver: LocationResolver) -> None:
    assert resolver.resolve("Yokneam", "IL") == "IL"  # Comeet's location.country, Workday's alpha2Code
    assert resolver.resolve("", "ISR") == "IL"
    assert resolver.resolve("London", "United Kingdom") == "GB"
    assert resolver.resolve("Tel Aviv", "nowhere") == "IL"  # an unknown field falls back to the text
