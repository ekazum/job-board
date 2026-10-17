"""PostingPatch validation and the outcome rule in apply_to."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.models.posting import Posting
from job_board.models.posting_patch import PostingPatch


def _posting(status: Status = Status.NEW, outcome: Outcome | None = None) -> Posting:
    return Posting(
        id=1,
        source=Source.MANUAL,
        external_id="https://acme.com/jobs/1",
        company="Acme",
        title="Backend Engineer",
        url="https://acme.com/jobs/1",
        text="",
        status=status,
        outcome=outcome,
        note="first note",
        created_at=datetime(2026, 10, 17, tzinfo=UTC),
    )


@pytest.mark.parametrize("status", ["new", "applied", "interview"])
def test_outcome_with_open_status_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        PostingPatch.model_validate({"status": status, "outcome": "rejected"})


def test_outcome_with_closed_status_accepted() -> None:
    patch = PostingPatch.model_validate({"status": "closed", "outcome": "offer"})
    assert (patch.status, patch.outcome) == (Status.CLOSED, Outcome.OFFER)


def test_unknown_outcome_rejected() -> None:
    with pytest.raises(ValidationError):
        PostingPatch.model_validate({"status": "closed", "outcome": "ghosted"})


def test_empty_patch_changes_nothing() -> None:
    current = _posting(Status.CLOSED, Outcome.REJECTED)
    assert PostingPatch.model_validate({}).apply_to(current) == current


def test_closing_with_outcome() -> None:
    updated = PostingPatch.model_validate({"status": "closed", "outcome": "withdrawn"}).apply_to(_posting())
    assert (updated.status, updated.outcome) == (Status.CLOSED, Outcome.WITHDRAWN)


def test_leaving_closed_clears_outcome() -> None:
    updated = PostingPatch.model_validate({"status": "applied"}).apply_to(_posting(Status.CLOSED, Outcome.REJECTED))
    assert (updated.status, updated.outcome) == (Status.APPLIED, None)


def test_note_only_patch_keeps_closed_outcome() -> None:
    updated = PostingPatch.model_validate({"note": "recruiter called"}).apply_to(_posting(Status.CLOSED, Outcome.OFFER))
    assert (updated.status, updated.outcome, updated.note) == (Status.CLOSED, Outcome.OFFER, "recruiter called")


def test_outcome_alone_on_closed_posting_changes_it() -> None:
    updated = PostingPatch.model_validate({"outcome": "offer"}).apply_to(_posting(Status.CLOSED, Outcome.REJECTED))
    assert updated.outcome is Outcome.OFFER


def test_explicit_null_outcome_clears_it() -> None:
    updated = PostingPatch.model_validate({"outcome": None}).apply_to(_posting(Status.CLOSED, Outcome.REJECTED))
    assert (updated.status, updated.outcome) == (Status.CLOSED, None)


def test_outcome_alone_on_open_posting_rejected() -> None:
    with pytest.raises(ValueError, match="this posting is 'applied'"):
        PostingPatch.model_validate({"outcome": "offer"}).apply_to(_posting(Status.APPLIED))


def test_null_note_means_unchanged_and_empty_note_clears() -> None:
    assert PostingPatch.model_validate({"note": None}).apply_to(_posting()).note == "first note"
    assert PostingPatch.model_validate({"note": ""}).apply_to(_posting()).note == ""
