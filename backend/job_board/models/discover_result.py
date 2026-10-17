"""Counts returned by a discover run."""

from pydantic import BaseModel

from job_board.models.run_issue import RunIssue


class DiscoverResult(BaseModel):
    """companies = verified + unverified + no_platform + len(issues).

    verified: board API answered 200 with a jobs array. unverified: a board link was found on the careers
    page but its API did not confirm it. no_platform: nothing found (stored as platform=none). issues:
    companies skipped because a board could not be reached; their stored row is left as it was.
    """

    companies: int
    verified: int
    unverified: int
    no_platform: int
    issues: list[RunIssue]
