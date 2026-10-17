"""Paste-form request model."""

from pydantic import BaseModel, ConfigDict, Field


class PostingCreate(BaseModel):
    """A posting pasted by hand; stored with source=manual and external_id=normalized URL."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    text: str = ""
