"""How far a scan has got."""

from pydantic import BaseModel, ConfigDict


class ScanProgress(BaseModel):
    """boards_done of boards read (failed of them could not be), then scored of to_score new jobs scored and stored
    in New; duration_s once the scan ends."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)  # every field is in every response

    boards_done: int = 0
    boards: int = 0
    failed: int = 0
    scored: int = 0
    to_score: int = 0
    duration_s: float | None = None
