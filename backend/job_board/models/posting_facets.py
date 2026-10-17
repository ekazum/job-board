"""What the filter bar can offer, and the board's unfiltered column totals."""

from pydantic import BaseModel

from job_board.enums.source import Source
from job_board.enums.status import Status


class PostingFacets(BaseModel):
    """companies and sources that have postings, and how many postings each status column holds unfiltered."""

    companies: list[str]
    sources: list[Source]
    totals: dict[Status, int]
