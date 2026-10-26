"""The board's tools that change it, served over MCP beside the read-only ones. The chat agent asks the user to
confirm every call first; other MCP clients ask with their own permission prompts (the tools are not marked
read-only)."""

from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import Field

from job_board.enums.outcome import Outcome
from job_board.enums.status import Status
from job_board.models.posting import Posting
from job_board.models.posting_patch import PostingPatch
from job_board.storage.posting_repository import PostingRepository
from job_board.tools.compact_json import compact_json

MOVE_POSTING = "move_posting"
CLOSE_POSTING = "close_posting"
ADD_NOTE = "add_note"
START_SCAN = "start_scan"
NOTE_CHARS = 2000
PostingId = Annotated[int, Field(description="The posting's id, the number in #42")]
# Spelled out rather than Status and Outcome: an enum parameter becomes a $ref in the schema, which small local
# models read poorly.
StatusName = Literal["new", "applied", "interview", "closed"]
OutcomeName = Literal["rejected", "withdrawn", "offer", "not_relevant"]


class BoardActions:
    """move_posting, close_posting, add_note and start_scan over the postings and the scan runner. Each answers with
    the posting as it now is (start_scan: that it started); a posting that does not exist is an error."""

    def __init__(self, postings: PostingRepository, scan_starter: Callable[[], bool]) -> None:
        self._postings = postings
        self._scan_starter = scan_starter

    def tools(self) -> list[Callable[..., str]]:
        """Every tool, for the MCP server."""
        return [self.move_posting, self.close_posting, self.add_note, self.start_scan]

    def move_posting(
        self, posting_id: PostingId, status: Annotated[StatusName, Field(description="The column to move it to")]
    ) -> str:
        """Move a posting to another board column: new, applied, interview or closed. Moving it out of closed clears
        its outcome; to close it with a reason use close_posting."""
        return self._saved(PostingPatch(status=Status(status)).apply_to(self._get(posting_id)))

    def close_posting(
        self,
        posting_id: PostingId,
        outcome: Annotated[
            OutcomeName,
            Field(
                description="rejected (the company said no), withdrawn (the user dropped it), offer, or not_relevant"
            ),
        ],
    ) -> str:
        """Close a posting with how it ended."""
        return self._saved(PostingPatch(status=Status.CLOSED, outcome=Outcome(outcome)).apply_to(self._get(posting_id)))

    def add_note(
        self,
        posting_id: PostingId,
        text: Annotated[str, Field(description="What to add to the note", min_length=1, max_length=NOTE_CHARS)],
    ) -> str:
        """Add a line to a posting's note; what the note says already is kept."""
        current = self._get(posting_id)
        note = f"{current.note.rstrip()}\n{text.strip()}" if current.note.strip() else text.strip()
        return self._saved(PostingPatch(note=note).apply_to(current))

    def start_scan(self) -> str:
        """Start a scan: read every company's job board and add the matching new jobs to New. It runs in the
        background, and scoring the new jobs takes a while."""
        if not self._scan_starter():
            raise ValueError("a scan or discover run is already in progress")
        return compact_json({"started": True})

    def _get(self, posting_id: int) -> Posting:
        """The posting; ValueError when there is none."""
        posting = self._postings.get(posting_id)
        if posting is None:
            raise ValueError(f"there is no posting #{posting_id}")
        return posting

    def _saved(self, posting: Posting) -> str:
        """Save the changed posting and answer with what it now is."""
        saved = self._postings.save(posting)
        if saved is None:
            raise ValueError(f"there is no posting #{posting.id}")
        return compact_json(
            {
                "id": saved.id,
                "title": saved.title,
                "company": saved.company,
                "status": saved.status,
                "outcome": saved.outcome,
                "note": saved.note,
            }
        )
