"""The candidate profile the scorer, the role filter and the location rule read."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from job_board.rules.location_resolver import LocationResolver


class Profile(BaseModel):
    """cv_text is extracted from the uploaded CV (and editable); targets says what the candidate is looking for.

    include_keywords and exclude_keywords are the job-title words or phrases wanted and excluded (see KeywordFilter);
    location (a country or a city) and allow_fully_remote decide which postings are kept (see LocationRule). The
    profile starts blank with no keywords (every title passes) and an empty location, so no posting passes until you
    set one.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)  # every field is in every response

    cv_text: str = ""
    targets: str = ""
    filename: str | None = None
    uploaded_at: datetime | None = None
    location: str = ""
    allow_fully_remote: bool = False
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def country(self) -> str | None:
        """The country (or countries) the location resolves to, e.g. "IL"; None when it does not resolve."""
        return LocationResolver.shared().resolve(self.location) if self.location.strip() else None
