"""Company update request model."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel

from job_board.utils.domains import web_url_or_none


class CompanyPatch(BaseModel):
    """Fields a client may change on a company; fields left out of the request stay as they are.
    careers_url set to null or "" clears it."""

    enabled: bool | None = None
    careers_url: Annotated[str | None, AfterValidator(web_url_or_none)] = None
