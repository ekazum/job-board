"""Progress of a Re-score all run."""

from pydantic import BaseModel


class RescoreStatus(BaseModel):
    """done of total postings scored so far; running is false before the first run and after one finishes."""

    running: bool
    done: int
    total: int
    error: str | None = None
