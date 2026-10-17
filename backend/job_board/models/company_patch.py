"""Company update request model."""

from pydantic import BaseModel


class CompanyPatch(BaseModel):
    """Fields a client may change on a company; fields left out of the request stay as they are."""

    enabled: bool | None = None
