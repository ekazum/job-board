"""Result of a discover or scan run."""

from pydantic import BaseModel


class RunSummary(BaseModel):
    """ok: companies processed; failed: companies whose error was saved to companies.last_error; duration_s: wall time."""

    ok: int
    failed: int
    duration_s: float
