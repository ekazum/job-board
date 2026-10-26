"""Result of applying the profile's job-title keywords and location to the stored postings."""

from pydantic import BaseModel


class SweepResult(BaseModel):
    """archived: postings moved from New to the Archive; restored: postings the sweep had archived, back in New."""

    archived: int
    restored: int
