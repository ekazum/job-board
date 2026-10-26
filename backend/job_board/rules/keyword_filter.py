"""Role filter for scanned jobs, matched against the job title; the phrases come from the Profile."""

from __future__ import annotations

import re
from collections.abc import Sequence

from job_board.models.profile import Profile

ALL_OF_SEPARATOR = " + "
REASON_PREFIX = "keywords: "  # also matched in sql/postings/*.sql ('keywords: %')
NO_WANTED_ROLE = f"{REASON_PREFIX}no wanted role in the title"

Entry = tuple[str, tuple[re.Pattern[str], ...]]


class KeywordFilter:
    """Case-insensitive whole-word matching on the job title.

    A title passes when it matches at least one include entry and no exclude entry (an empty include list lets
    every title through). An entry is a word or a phrase: "Engineering Director" matches "Engineering Director, AI"
    but not "Director of Engineering". An entry "a + b" matches when the title contains every part, in any order:
    "AI + engineer" matches "Senior AI Infrastructure Engineer" but not "AI Sales Lead". Word edges are
    (?<!\\w)/(?!\\w) rather than \\b so "c++" and ".net" work, and spaces inside a part match any run of whitespace.

    A stored posting whose title fails (after the keywords changed) is closed as not_relevant with fit_reason
    "keywords: ...", which puts it in the Archive (see ProfileSweep).
    """

    def __init__(self, include: Sequence[str], exclude: Sequence[str]) -> None:
        self._include = self._compile(include)
        self._exclude = self._compile(exclude)
        self._search_terms = tuple(
            " ".join(self._parts(entry)) for entry in include if self._parts(entry)
        )

    @classmethod
    def for_profile(cls, profile: Profile | None) -> KeywordFilter:
        """The filter the profile's job-title keywords describe (a blank profile lets every title through)."""
        settings = profile or Profile()
        return cls(settings.include_keywords, settings.exclude_keywords)

    @property
    def search_terms(self) -> tuple[str, ...]:
        """The include entries as plain search text ("AI + engineer" -> "AI engineer"), for sites searched by keyword."""
        return self._search_terms

    def matches(self, title: str) -> bool:
        """True when a job with this title should become a card."""
        return self.rejection(title) is None

    def rejection(self, title: str) -> str | None:
        """None when the title passes, else the fit_reason to store with it ('keywords: excludes "intern"')."""
        excluded = next((text for text, parts in self._exclude if self._matches_entry(parts, title)), None)
        if excluded is not None:
            return f'{REASON_PREFIX}excludes "{excluded}"'
        if self._include and not any(self._matches_entry(parts, title) for _, parts in self._include):
            return NO_WANTED_ROLE
        return None

    @staticmethod
    def is_rejection(reason: str | None) -> bool:
        """Whether a fit_reason is one this filter wrote."""
        return reason is not None and reason.startswith(REASON_PREFIX)

    @staticmethod
    def _matches_entry(parts: tuple[re.Pattern[str], ...], title: str) -> bool:
        """Every part of one entry appears in the title."""
        return all(part.search(title) is not None for part in parts)

    @staticmethod
    def _parts(entry: str) -> list[str]:
        """The non-blank parts of an "a + b" entry."""
        return [part.strip() for part in entry.split(ALL_OF_SEPARATOR) if part.strip()]

    @staticmethod
    def _compile(entries: Sequence[str]) -> tuple[Entry, ...]:
        """Each entry with its whole-word patterns, one per part; blank entries are dropped."""
        compiled: list[Entry] = []
        for entry in entries:
            parts = KeywordFilter._parts(entry)
            if parts:
                compiled.append((entry.strip(), tuple(KeywordFilter._word(part) for part in parts)))
        return tuple(compiled)

    @staticmethod
    def _word(part: str) -> re.Pattern[str]:
        """A whole-word, case-insensitive pattern for one part."""
        escaped = re.escape(part).replace(r"\ ", r"\s+")
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
