"""Result of applying the location rule to the stored postings."""

from pydantic import BaseModel


class LocationSweepResult(BaseModel):
    """archived: postings moved from New to the Archive; restored: postings the rule had archived, back in New."""

    archived: int
    restored: int
