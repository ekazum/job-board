"""Posting outcome enum."""

from enum import StrEnum


class Outcome(StrEnum):
    """Why a posting was closed; set only when its status is closed."""

    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    OFFER = "offer"
    NOT_RELEVANT = "not_relevant"
