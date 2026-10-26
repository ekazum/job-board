"""Run a scan in the background."""

import asyncio
import logging
from collections.abc import Callable

from job_board.models.run_summary import RunSummary
from job_board.models.scan_progress import ScanProgress
from job_board.models.scan_status import ScanStatus
from job_board.runs.scan import Scan

logger = logging.getLogger(__name__)


class ScanJob:
    """One scan at a time as a background task whose progress status() reports, so the request that starts it answers
    at once. Each scan is built fresh by scan_factory (edits to config.yaml apply) and stores every new job as soon as
    it is scored, so a scan that stops early keeps what it scored and the next one picks up the rest.
    """

    def __init__(self, scan_factory: Callable[[], Scan]) -> None:
        self._scan_factory = scan_factory
        self._scan: Scan | None = None
        self._task: asyncio.Task[RunSummary] | None = None
        self._error: str | None = None

    @property
    def running(self) -> bool:
        """Whether a scan is in progress."""
        return self._task is not None and not self._task.done()

    def status(self) -> ScanStatus:
        """Progress of the current or last scan."""
        progress = ScanProgress() if self._scan is None else self._scan.progress
        return ScanStatus(**progress.model_dump(), running=self.running, error=self._error)

    def start(self) -> bool:
        """Begin a scan in the background; False when one is already going."""
        if self.running:
            return False
        self._scan, self._error = self._scan_factory(), None
        self._task = asyncio.create_task(self._scan.run())
        self._task.add_done_callback(self._finished)
        return True

    def _finished(self, task: asyncio.Task[RunSummary]) -> None:
        """Keep the reason a scan stopped early, for status()."""
        if task.cancelled():
            self._error = "cancelled"
        elif task.exception() is not None:
            self._error = f"{type(task.exception()).__name__}: {task.exception()}"
            logger.error("scan stopped: %s", self._error)
