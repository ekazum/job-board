"""Company update request model."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel

from job_board.utils.domains import bare_domain_or_none, web_url_or_none


class CompanyPatch(BaseModel):
    """Fields a client may change on a company; fields left out of the request stay as they are.
    careers_url or domain set to null or "" clears it. The domain is stored bare ("https://www.Acme.com" -> "acme.com")
    and Discover starts from it."""

    enabled: bool | None = None
    careers_url: Annotated[str | None, AfterValidator(web_url_or_none)] = None
    domain: Annotated[str | None, AfterValidator(bare_domain_or_none)] = None
