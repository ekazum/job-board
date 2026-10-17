"""Role filter for scanned jobs, matched against the job title."""

import re
from collections.abc import Sequence

ALL_OF_SEPARATOR = " + "


class KeywordFilter:
    """Case-insensitive whole-word matching on the job title.

    A title passes when it matches at least one include entry and no exclude entry (an empty include list lets
    every title through). An entry "a + b" matches when the title contains every part, in any order:
    "AI + engineer" matches "Senior AI Infrastructure Engineer" but not "AI Sales Lead". Word edges are
    (?<!\\w)/(?!\\w) rather than \\b so "c++" and ".net" work, and spaces inside a part match any run of whitespace.
    """

    def __init__(self, include: Sequence[str], exclude: Sequence[str]) -> None:
        self._include = self._compile(include)
        self._exclude = self._compile(exclude)
        self._search_terms = tuple(
            " ".join(self._parts(entry)) for entry in include if self._parts(entry)
        )

    @property
    def search_terms(self) -> tuple[str, ...]:
        """The include entries as plain search text ("AI + engineer" -> "AI engineer"), for sites searched by keyword."""
        return self._search_terms

    def matches(self, title: str) -> bool:
        """True when a job with this title should become a card."""
        if any(self._matches_entry(entry, title) for entry in self._exclude):
            return False
        return not self._include or any(self._matches_entry(entry, title) for entry in self._include)

    @staticmethod
    def _matches_entry(entry: tuple[re.Pattern[str], ...], title: str) -> bool:
        """Every part of one entry appears in the title."""
        return all(part.search(title) is not None for part in entry)

    @staticmethod
    def _parts(entry: str) -> list[str]:
        """The non-blank parts of an "a + b" entry."""
        return [part.strip() for part in entry.split(ALL_OF_SEPARATOR) if part.strip()]

    @staticmethod
    def _compile(entries: Sequence[str]) -> tuple[tuple[re.Pattern[str], ...], ...]:
        """Each entry as a tuple of whole-word patterns, one per part; blank entries are dropped."""
        compiled: list[tuple[re.Pattern[str], ...]] = []
        for entry in entries:
            parts = KeywordFilter._parts(entry)
            if parts:
                compiled.append(tuple(KeywordFilter._word(part) for part in parts))
        return tuple(compiled)

    @staticmethod
    def _word(part: str) -> re.Pattern[str]:
        """A whole-word, case-insensitive pattern for one part."""
        escaped = re.escape(part).replace(r"\ ", r"\s+")
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
