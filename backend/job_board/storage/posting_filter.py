"""Value object for the board's filter bar."""

from dataclasses import dataclass, field

from job_board.enums.source import Source


@dataclass(frozen=True)
class PostingFilter:
    """Which postings the board shows; empty fields do not filter. text matches the title (and the description too
    when in_text), as a case-insensitive substring. min_fit keeps postings scored at least that high plus every
    posting not scored yet. location is a substring of the location, spellings normalized ("tel-aviv" finds
    "Tel Aviv-Yafo"). archived selects the Archive instead of the board: postings the scorer or the location rule
    closed as not relevant."""

    text: str = ""
    in_text: bool = False
    companies: tuple[str, ...] = field(default=())
    sources: tuple[Source, ...] = field(default=())
    min_fit: int | None = None
    location: str = ""
    archived: bool = False
