"""HTTP endpoints that trigger discover and scan runs."""

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from job_board.discover import Discover
from job_board.models.run_summary import RunSummary
from job_board.scan import Scan

BUSY_RESPONSE: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"description": "Another discover or scan run is in progress"}
}


class RunRoutes:
    """POST /api/discover and POST /api/scan, each returning {ok, failed, duration_s}.

    Runs are async, so the board keeps answering while one is in progress; only one runs at a time and a second
    request gets 409. Each run is built fresh by its factory, so edits to config.yaml apply without a restart.
    """

    def __init__(self, discover_factory: Callable[[], Discover], scan_factory: Callable[[], Scan]) -> None:
        self._discover_factory = discover_factory
        self._scan_factory = scan_factory
        self._lock = asyncio.Lock()

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api", tags=["runs"])
        router.add_api_route("/discover", self.run_discover, methods=["POST"], responses=BUSY_RESPONSE)
        router.add_api_route("/scan", self.run_scan, methods=["POST"], responses=BUSY_RESPONSE)
        return router

    async def run_discover(self) -> RunSummary:
        """Discover the careers platform of every company."""
        return await self._exclusive(self._discover_factory)

    async def run_scan(self) -> RunSummary:
        """Scan verified, enabled companies and add matching jobs as new cards."""
        return await self._exclusive(self._scan_factory)

    async def _exclusive(self, factory: Callable[[], Discover | Scan]) -> RunSummary:
        """Run while holding the lock; 409 if a run already holds it."""
        if self._lock.locked():
            raise HTTPException(status.HTTP_409_CONFLICT, "a discover or scan run is already in progress")
        async with self._lock:
            return await factory().run()
