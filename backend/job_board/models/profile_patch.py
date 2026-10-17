"""Profile edit request model."""

from pydantic import BaseModel, field_validator


class ProfilePatch(BaseModel):
    """Fields left out (or null) stay as they are; location is trimmed."""

    cv_text: str | None = None
    targets: str | None = None
    location: str | None = None
    allow_fully_remote: bool | None = None

    @field_validator("location")
    @classmethod
    def _trimmed(cls, location: str | None) -> str | None:
        """The location without surrounding spaces."""
        return None if location is None else location.strip()
