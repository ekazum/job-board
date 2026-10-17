"""Posting response model."""

from datetime import datetime

from pydantic import BaseModel

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
