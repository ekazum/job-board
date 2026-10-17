"""Result of Purge rejects."""

from pydantic import BaseModel


class PurgeResult(BaseModel):
    """deleted: postings removed for good."""

    deleted: int
