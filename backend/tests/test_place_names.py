"""PlaceNames: one spelling per place, so locations compare across boards."""

import pytest

from job_board.place_names import PlaceNames


@pytest.mark.parametrize(
    ("spelling", "normalized"),
    [
        ("Tel-Aviv", "tel aviv"),
        ("Tel Aviv-Yafo", "tel aviv"),
        ("TEL AVIV-JAFFA, Israel", "tel aviv israel"),
        ("Tel Aviv‐Yafo", "tel aviv"),  # a Unicode hyphen
        ("Petach Tikva", "petah tikva"),
        ("Petah Tiqwa", "petah tikva"),
        ("Petaẖ Tiqva", "petah tikva"),  # geonamescache's own spelling
        ("Ra'anana", "raanana"),
        ("Ra’anana", "raanana"),
        ("Raanana", "raanana"),
        ("Herzelia", "herzliya"),
        ("Israël", "israel"),
        ("תל אביב", "tel aviv"),
        ("Work from home", "remote"),
        ("", ""),
    ],
)
def test_spellings_of_a_place_normalize_alike(spelling: str, normalized: str) -> None:
    assert PlaceNames.normalize(spelling) == normalized


def test_place_words_leave_out_remote_and_its_companions() -> None:
    assert PlaceNames.place_words("Remote - US") == "us"
    assert PlaceNames.place_words("100% Remote (anywhere)") == ""
    assert PlaceNames.place_words("Israel, Multiple Locations") == "israel"
