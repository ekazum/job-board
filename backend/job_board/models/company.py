"""Company response model."""

from datetime import datetime

from pydantic import BaseModel

from job_board.enums.platform import Platform


class Company(BaseModel):
    """A company as stored in the companies table; platform is None until discovery has run.

    last_error is the reason the latest discover or scan failed for this company, cleared when one succeeds.
    """

    id: int
    name: str
    domain: str | None
    careers_url: str | None
    platform: Platform | None
    slug: str | None
    verified: bool
    enabled: bool
    last_checked: datetime | None
    last_error: str | None
