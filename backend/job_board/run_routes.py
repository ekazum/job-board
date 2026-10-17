"""HTTP endpoints that trigger discover and scan runs."""

import threading
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from job_board.discover import Discover
from job_board.models.discover_result import DiscoverResult
from job_board.models.scan_result import ScanResult
from job_board.scan import Scan

BUSY_RESPONSE: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"description": "Another discover or scan run is in progress"}
}


class RunRoutes:
    """POST /api/discover and POST /api/scan. Runs are synchronous (the endpoints are plain `def`, so FastAPI
    runs them in its thread pool and the board stays responsive) and one at a time: a second request while
    a run is in progress gets 409. Each run is built fresh by its factory, so edits to config.yaml apply
    without a restart."""

    def __init__(self, discover_factory: Callable[[], Discover], scan_factory: Callable[[], Scan]) -> None:
        self._discover_factory = discover_factory
        self._scan_factory = scan_factory
        self._lock = threading.Lock()

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api", tags=["runs"])
        router.add_api_route("/discover", self.run_discover, methods=["POST"], responses=BUSY_RESPONSE)
        router.add_api_route("/scan", self.run_scan, methods=["POST"], responses=BUSY_RESPONSE)
        return router

    def run_discover(self) -> DiscoverResult:
        """Discover the careers platform of every company in config.yaml."""
        return self._exclusive(lambda: self._discover_factory().run())

    def run_scan(self) -> ScanResult:
        """Scan verified, enabled companies and add matching jobs as new cards."""
        return self._exclusive(lambda: self._scan_factory().run())

    def _exclusive[T](self, run: Callable[[], T]) -> T:
        """Run while holding the lock; 409 if it is already held."""
        if not self._lock.acquire(blocking=False):
            raise HTTPException(status.HTTP_409_CONFLICT, "a discover or scan run is already in progress")
        try:
            return run()
        finally:
            self._lock.release()
