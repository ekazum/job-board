"""The candidate profile the scorer and the location rule read."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from job_board.location_resolver import LocationResolver


class Profile(BaseModel):
    """cv_text is extracted from the uploaded CV (and editable); targets says what the candidate is looking for.

    location (a country or a city) and allow_fully_remote decide which postings are kept (see LocationRule). The
    profile starts blank with an empty location, so no posting passes until you set one.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)  # every field is in every response

    cv_text: str = ""
    targets: str = ""
    filename: str | None = None
    uploaded_at: datetime | None = None
    location: str = ""
    allow_fully_remote: bool = False

    @computed_field
    @property
    def country(self) -> str | None:
        """The country (or countries) the location resolves to, e.g. "IL"; None when it does not resolve."""
        return LocationResolver.shared().resolve(self.location) if self.location.strip() else None
