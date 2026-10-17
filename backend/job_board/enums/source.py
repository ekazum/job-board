"""Posting source enum."""

from enum import StrEnum


class Source(StrEnum):
    """Where a posting came from: a scanned platform, or pasted by hand."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    COMEET = "comeet"
    WORKDAY = "workday"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    APPLE = "apple"
    AMAZON = "amazon"
    META = "meta"
    MANUAL = "manual"
