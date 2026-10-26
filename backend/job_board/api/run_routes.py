"""HTTP endpoints that trigger discover and scan runs."""

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from job_board.models.discover_summary import DiscoverSummary
from job_board.models.scan_status import ScanStatus
from job_board.runs.discover import Discover
from job_board.runs.scan import Scan
from job_board.runs.scan_job import ScanJob

BUSY_RESPONSE: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"description": "Another discover or scan run is in progress"}
}


class RunRoutes:
    """POST /api/discover answers {ok, failed, duration_s, added} when the run is done; POST /api/scan starts a scan in
    the background (202) and GET /api/scan/status reports how far it has got.

    Runs are async, so the board keeps answering while one is in progress; only one runs at a time and a second
    request gets 409. Each run is built fresh by its factory, so edits to config.yaml apply without a restart.
    """

    def __init__(self, discover_factory: Callable[[], Discover], scan_factory: Callable[[], Scan]) -> None:
        self._discover_factory = discover_factory
        self._scan_job = ScanJob(scan_factory)
        self._lock = asyncio.Lock()

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api", tags=["runs"])
        router.add_api_route("/discover", self.run_discover, methods=["POST"], responses=BUSY_RESPONSE)
        router.add_api_route(
            "/scan", self.run_scan, methods=["POST"], status_code=status.HTTP_202_ACCEPTED, responses=BUSY_RESPONSE
        )
        router.add_api_route("/scan/status", self.scan_status, methods=["GET"])
        return router

    async def run_discover(self) -> DiscoverSummary:
        """Add the companies of pasted postings to the list, then discover the careers platform of every company."""
        if self._lock.locked() or self._scan_job.running:
            raise self._busy()
        async with self._lock:
            return await self._discover_factory().run()

    async def run_scan(self) -> ScanStatus:
        """Start scanning verified, enabled companies; matching jobs arrive as cards while it runs."""
        if not self.start_scan():
            raise self._busy()
        return self._scan_job.status()

    def start_scan(self) -> bool:
        """Begin a scan in the background (the Scan button, the chat's start_scan); False while a discover or scan run
        is in progress."""
        return not self._lock.locked() and self._scan_job.start()

    def scan_status(self) -> ScanStatus:
        """Progress of the current or last scan."""
        return self._scan_job.status()

    @staticmethod
    def _busy() -> HTTPException:
        """The 409 for a run requested while another one is in progress."""
        return HTTPException(status.HTTP_409_CONFLICT, "a discover or scan run is already in progress")
