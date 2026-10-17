"""Posting response model."""

from datetime import datetime

from pydantic import BaseModel, Field

from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status


class Posting(BaseModel):
    """A job posting as stored in the postings table and returned by the API."""

    id: int
    source: Source
    external_id: str
    company: str
    title: str
    url: str
    text: str
    status: Status
    outcome: Outcome | None
    note: str
    created_at: datetime
    fit: int | None = None  # LLM fit score 0-10; None until the posting has been scored
    location: str = ""
    fit_reason: str | None = None  # the scorer's one-line reason, or why it could not score
    fit_gaps: list[str] = Field(default_factory=list)  # requirements the candidate does not meet
    is_remote: bool = False  # the posting says it is remote (location, title, or a fully-remote phrase)
    country: str | None = None  # ISO 3166-1 alpha-2 code(s) of the location, "IL" or "DE,IL"; None when unknown
