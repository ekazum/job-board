"""Posting update request model."""

from typing import Self

from pydantic import BaseModel, model_validator

from job_board.enums.outcome import Outcome
from job_board.enums.status import Status
from job_board.models.posting import Posting


class PostingPatch(BaseModel):
    """Fields a client may change on a posting; fields left out of the request stay as they are.

    Outcome rule: an outcome exists only on a closed posting. Moving a posting out of closed clears its
    outcome; sending an outcome for a posting that is (or would be) open is rejected.
    """

    status: Status | None = None
    outcome: Outcome | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _outcome_requires_closed(self) -> Self:
        """Reject an outcome paired with any status other than closed."""
        if self.outcome is not None and self.status is not None and self.status is not Status.CLOSED:
            raise ValueError(f"outcome is allowed only when status is '{Status.CLOSED}'")
        return self

    def apply_to(self, current: Posting) -> Posting:
        """Return the posting with this patch applied; raises ValueError when the outcome rule is broken."""
        status = current.status if self.status is None else self.status
        if "outcome" in self.model_fields_set:
            outcome = self.outcome
        elif status is Status.CLOSED:
            outcome = current.outcome
        else:
            outcome = None
        if outcome is not None and status is not Status.CLOSED:
            raise ValueError(f"outcome is allowed only when status is '{Status.CLOSED}'; this posting is '{status}'")
        note = current.note if self.note is None else self.note
        return current.model_copy(update={"status": status, "outcome": outcome, "note": note})
