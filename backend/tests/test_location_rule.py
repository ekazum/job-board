"""LocationRule: the profile's location (resolved to a country) and allow_fully_remote decide which postings pass."""

import pytest

from job_board.rules.location_resolver import LocationResolver
from job_board.rules.location_rule import LocationRule

ISRAEL = LocationRule("Israel")
ISRAEL_OR_REMOTE = LocationRule("Israel", allow_fully_remote=True)


def _rejection(rule: LocationRule, location: str, title: str = "AI Engineer", text: str = "") -> str | None:
    """The rule's verdict on a posting whose country is resolved from its location, as a scan stores it."""
    country = LocationResolver.shared().resolve(location)
    return rule.rejection(country=country, location=location, title=title, text=text)


@pytest.mark.parametrize("location", ["Tel Aviv-Yafo", "Herzliya", "Petach Tikva", "Israel, Raanana", "Berlin / Tel Aviv"])
def test_postings_in_the_profile_country_pass(location: str) -> None:
    assert _rejection(ISRAEL, location) is None


@pytest.mark.parametrize("location", ["Berlin", "Remote - US", "London, United Kingdom", "Remote"])
def test_postings_elsewhere_are_rejected_with_their_location(location: str) -> None:
    assert _rejection(ISRAEL, location) == f"location: {location}"


def test_a_city_as_the_profile_location_stands_for_its_country() -> None:
    assert _rejection(LocationRule("Tel Aviv"), "Haifa, Israel") is None
    assert _rejection(LocationRule("Tel Aviv"), "Berlin") == "location: Berlin"


def test_without_a_location_the_title_or_text_must_name_the_profile_location() -> None:
    assert _rejection(ISRAEL, "", text="You will join our R&D center in Israel.") is None
    assert _rejection(ISRAEL, "", title="AI Engineer, Israel") is None
    assert _rejection(ISRAEL, "", text="Join our team.") == "location: (not given)"


def test_an_unresolved_location_falls_back_to_the_profile_location_string() -> None:
    assert _rejection(ISRAEL, "Gush Dan", text="Hybrid work in central Israel.") is None
    assert _rejection(ISRAEL, "Gush Dan") == "location: Gush Dan"
    assert _rejection(LocationRule("EMEA"), "Remote (EMEA)") is None  # the profile location resolves to no country


def test_fully_remote_postings_pass_only_with_the_toggle() -> None:
    assert _rejection(ISRAEL, "Remote") == "location: Remote"
    assert _rejection(ISRAEL_OR_REMOTE, "Remote") is None
    assert _rejection(ISRAEL_OR_REMOTE, "", title="AI Engineer (Remote)") is None
    assert _rejection(ISRAEL_OR_REMOTE, "Anywhere", text="This role is fully remote.") is None


def test_remote_with_a_place_outside_the_profile_country_fails() -> None:
    assert _rejection(ISRAEL_OR_REMOTE, "Remote - US") == "location: Remote - US"
    assert _rejection(ISRAEL_OR_REMOTE, "London (remote)") == "location: London (remote)"
    assert _rejection(ISRAEL_OR_REMOTE, "Remote", title="AI Engineer (Remote - Europe)") == "location: Remote"
    assert _rejection(ISRAEL_OR_REMOTE, "Anywhere, Germany", text="Fully remote.") == "location: Anywhere, Germany"
    assert _rejection(ISRAEL_OR_REMOTE, "Remote - Israel") is None  # the place is the profile's country


def test_no_profile_location_lets_nothing_pass() -> None:
    assert _rejection(LocationRule.for_profile(None), "Tel Aviv, Israel") == "location: Tel Aviv, Israel"
    assert _rejection(LocationRule("", allow_fully_remote=True), "Remote") == "location: Remote"


@pytest.mark.parametrize(
    ("location", "title", "text", "remote"),
    [
        ("Remote", "AI Engineer", "", True),
        ("Tel Aviv, Israel (remote)", "AI Engineer", "", True),
        ("", "AI Engineer - Remote", "", True),
        ("", "AI Engineer", "We work from anywhere.", True),
        ("Tel Aviv, Israel", "AI Engineer", "Remote-friendly team with offices in Tel Aviv.", False),
        ("Tel Aviv, Israel", "AI Engineer", "", False),
    ],
)
def test_is_remote(location: str, title: str, text: str, remote: bool) -> None:
    assert LocationRule.is_remote(location=location, title=title, text=text) is remote


def test_rejections_are_recognised_by_their_reason() -> None:
    assert LocationRule.is_rejection("location: Berlin")
    assert not LocationRule.is_rejection("far off") and not LocationRule.is_rejection(None)


def test_searched_sites_look_in_the_profile_locations_country() -> None:
    assert (ISRAEL.search_places, LocationRule("Haifa").search_places) == (("Israel",), ("Israel",))
    assert (LocationRule("EMEA").search_places, LocationRule("").search_places) == (("EMEA",), ())
