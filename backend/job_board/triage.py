"""Where a scored posting goes."""

from job_board.enums.outcome import Outcome
from job_board.enums.status import Status


class Triage:
    """A posting stays New when its fit reaches the threshold or it could not be scored (fit None); otherwise it is
    closed as not_relevant, which puts it in the Archive."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold

    def decide(self, fit: int | None) -> tuple[Status, Outcome | None]:
        """The status and outcome for a posting with this fit."""
        if fit is None or fit >= self._threshold:
            return Status.NEW, None
        return Status.CLOSED, Outcome.NOT_RELEVANT
