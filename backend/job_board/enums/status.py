"""Posting status enum."""

from enum import StrEnum


class Status(StrEnum):
    """Board column a posting sits in."""

    NEW = "new"
    APPLIED = "applied"
    INTERVIEW = "interview"
    CLOSED = "closed"
