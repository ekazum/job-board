"""Value object for one job read from a board."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobListing:
    """A job as read from a board, before filtering. text is plain text (HTML already stripped); location is the
    board's own wording ("Tel Aviv, Israel", "Israel, Raanana | Israel, Yokneam"), empty when it gives none; country
    is the board's own country field when it has one ("IL", "Israel"), for LocationResolver."""

    external_id: str
    title: str
    url: str
    text: str
    location: str = ""
    country: str = ""
