"""KeywordFilter: wanted roles and excluded roles, matched against the job title."""

import pytest

from job_board.keyword_filter import KeywordFilter

ROLES = KeywordFilter(
    include=["researcher", "AI + engineer", "VP + R&D", "director + data science", "architect", "CTO"],
    exclude=["intern", "product manager", "sales", "full stack"],
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Security Researcher", True),
        ("Senior AI Infrastructure Engineer", True),  # every part of "AI + engineer", any order
        ("Engineer, Applied AI", True),
        ("AI Sales Lead", False),  # AI without engineer
        ("VP R&D", True),
        ("VP of R&D", True),
        ("R&D VP", True),
        ("Director of Data Science", True),
        ("Data Science Director", True),
        ("Chief Architect", True),
        ("Field CTO", True),
        ("Backend Engineer", False),  # engineer without AI
        ("AI Research Intern", False),  # excluded role wins
        ("Principal AI Product Manager", False),
        ("Full Stack AI Engineer", False),
        ("Senior Data Scientist", False),
        ("Detector Engineer", False),  # whole words: "CTO" is not inside "Detector"
    ],
)
def test_roles(title: str, expected: bool) -> None:
    assert ROLES.matches(title) is expected


def test_empty_include_keeps_everything_not_excluded() -> None:
    keyword_filter = KeywordFilter(include=[], exclude=["sales"])
    assert keyword_filter.matches("Accountant")
    assert not keyword_filter.matches("Sales Manager")


def test_symbols_and_multi_word_parts() -> None:
    keyword_filter = KeywordFilter(include=["c++", ".net", "machine learning + engineer"], exclude=[])
    assert keyword_filter.matches("C++ Developer")
    assert keyword_filter.matches("Senior .NET Developer")
    assert keyword_filter.matches("Machine\nLearning Engineer")
    assert not keyword_filter.matches("C Developer")


def test_search_terms_are_the_entries_as_plain_text() -> None:
    assert KeywordFilter(["AI + engineer", "CTO", " + "], []).search_terms == ("AI engineer", "CTO")
