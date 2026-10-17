"""Include/exclude keyword matching for scanned jobs."""

import re
from collections.abc import Sequence


class KeywordFilter:
    """Case-insensitive whole-word matching on title + text.

    A job passes when no exclude keyword appears and at least one include keyword does; an empty include
    list lets everything through. Word edges are (?<!\\w)/(?!\\w) rather than \\b so "c++" and ".net" work,
    and spaces inside a keyword match any run of whitespace.
    """

    def __init__(self, include: Sequence[str], exclude: Sequence[str]) -> None:
        self._include = self._compile(include)
        self._exclude = self._compile(exclude)

    def matches(self, title: str, text: str) -> bool:
        """True when the job should become a card."""
        haystack = f"{title}\n{text}"
        if self._exclude is not None and self._exclude.search(haystack) is not None:
            return False
        return self._include is None or self._include.search(haystack) is not None

    @staticmethod
    def _compile(keywords: Sequence[str]) -> re.Pattern[str] | None:
        """One alternation of whole-word keywords, longest first; None for an empty list."""
        cleaned = sorted({keyword.strip() for keyword in keywords if keyword.strip()}, key=len, reverse=True)
        if not cleaned:
            return None
        escaped = (re.escape(keyword).replace(r"\ ", r"\s+") for keyword in cleaned)
        return re.compile("|".join(rf"(?<!\w){word}(?!\w)" for word in escaped), re.IGNORECASE)
