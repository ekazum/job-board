"""Profile edit request model."""

from pydantic import BaseModel, field_validator


class ProfilePatch(BaseModel):
    """Fields left out (or null) stay as they are; location is trimmed, and each keyword list is trimmed with blank
    entries and repeats (ignoring case) dropped."""

    cv_text: str | None = None
    targets: str | None = None
    location: str | None = None
    allow_fully_remote: bool | None = None
    include_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None

    @field_validator("location")
    @classmethod
    def _trimmed(cls, location: str | None) -> str | None:
        """The location without surrounding spaces."""
        return None if location is None else location.strip()

    @field_validator("include_keywords", "exclude_keywords")
    @classmethod
    def _distinct(cls, keywords: list[str] | None) -> list[str] | None:
        """The keywords trimmed, in order, without blanks or repeats."""
        if keywords is None:
            return None
        seen: set[str] = set()
        distinct: list[str] = []
        for keyword in (keyword.strip() for keyword in keywords):
            if keyword and keyword.casefold() not in seen:
                seen.add(keyword.casefold())
                distinct.append(keyword)
        return distinct
