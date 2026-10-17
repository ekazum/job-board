"""Counts returned by a scan run."""

from pydantic import BaseModel

from job_board.models.run_issue import RunIssue


class ScanResult(BaseModel):
    """companies: verified + enabled companies scanned. jobs_seen: jobs on their boards. matched: jobs that
    passed the keyword filter. added: matched jobs that were new (the rest were already on the board)."""

    companies: int
    jobs_seen: int
    matched: int
    added: int
    issues: list[RunIssue]
