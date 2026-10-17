"""Result of the Settings view's Test button."""

from pydantic import BaseModel


class LlmTestResult(BaseModel):
    """One tiny scoring request: raw is the model's answer exactly as received; error is set when it failed."""

    ok: bool
    provider: str
    model: str
    latency_ms: int
    raw: str
    error: str | None
