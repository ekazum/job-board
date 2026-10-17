"""KeywordFilter: include/exclude on title + text."""

import pytest

from job_board.keyword_filter import KeywordFilter


@pytest.mark.parametrize(
    ("title", "text", "expected"),
    [
        ("Backend Engineer", "", True),
        ("Software Engineer", "Our stack is Python and Postgres.", True),  # include found in text
        ("BACKEND engineer", "", True),  # case-insensitive
        ("Frontend Engineer", "React and TypeScript.", False),  # no include
        ("Backend Intern", "", False),  # exclude in title
        ("Backend Engineer", "You will mentor an intern.", False),  # exclude in text
        ("Backend Engineer", "Work on internal tools.", True),  # whole word: internal is not intern
        ("Pythonista wanted", "", False),  # whole word: Pythonista is not python
    ],
)
def test_include_exclude(title: str, text: str, expected: bool) -> None:
    keyword_filter = KeywordFilter(include=["backend", "python"], exclude=["intern"])
    assert keyword_filter.matches(title, text) is expected


def test_empty_include_keeps_everything_not_excluded() -> None:
    keyword_filter = KeywordFilter(include=[], exclude=["sales"])
    assert keyword_filter.matches("Accountant", "")
    assert not keyword_filter.matches("Sales Manager", "")


def test_symbols_and_multi_word_keywords() -> None:
    keyword_filter = KeywordFilter(include=["c++", ".net", "machine learning"], exclude=[])
    assert keyword_filter.matches("C++ Developer", "")
    assert keyword_filter.matches("Engineer", "Experience with .NET services")
    assert keyword_filter.matches("Machine\nLearning Engineer", "")
    assert not keyword_filter.matches("C Developer", "")
