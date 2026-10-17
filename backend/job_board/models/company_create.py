"""Add-company request model."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from job_board.utils.domains import bare_domain_or_none


class CompanyCreate(BaseModel):
    """A company added in the UI. With a domain it is included in the next Discover; discovery fills in
    platform, slug and verified. The domain is stored bare ("https://www.Acme.com/x" -> "acme.com")."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    domain: Annotated[str | None, AfterValidator(bare_domain_or_none)] = None
