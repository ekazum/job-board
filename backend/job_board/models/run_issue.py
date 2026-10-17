"""Problem reported by a discover or scan run."""

from pydantic import BaseModel


class RunIssue(BaseModel):
    """One company that could not be processed; the run carries on with the others."""

    company: str
    message: str
