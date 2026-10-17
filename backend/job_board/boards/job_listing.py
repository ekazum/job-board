"""Value object for one job read from a board."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobListing:
    """A job as read from a board, before keyword filtering. text is plain text (HTML already stripped)."""

    external_id: str
    title: str
    url: str
    text: str
