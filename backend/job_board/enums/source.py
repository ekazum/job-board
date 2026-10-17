"""Posting source enum."""

from enum import StrEnum


class Source(StrEnum):
    """Where a posting came from: a scanned platform, or pasted by hand."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    COMEET = "comeet"
    MANUAL = "manual"
