"""The LLM's answer when scoring a posting."""

from pydantic import BaseModel, ConfigDict, Field


class FitAssessment(BaseModel):
    """Exactly the JSON object prompts/score_system.txt asks for; anything else fails validation (a parse error)."""

    model_config = ConfigDict(extra="ignore")

    relevant: bool
    fit: int = Field(ge=0, le=10)
    reason: str
    gaps: list[str] = Field(default_factory=list)
