"""HTTP endpoints that re-score postings."""

from fastapi import APIRouter, HTTPException, status

from job_board.models.location_sweep_result import LocationSweepResult
from job_board.models.posting import Posting
from job_board.models.rescore_status import RescoreStatus
from job_board.rescore_job import RescoreJob


class RescoreRoutes:
    """POST /api/rescore applies the profile's location to every stored posting, then starts scoring in the
    background (202; 409 while a run is going); GET /api/rescore/status reports done/total; POST
    /api/rescore/locations applies the location only (409 while a run is going); POST /api/rescore/{posting_id} does
    both for one posting and returns it."""

    def __init__(self, job: RescoreJob) -> None:
        self._job = job

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/rescore", tags=["rescore"])
        router.add_api_route(
            "",
            self.start_rescore,
            methods=["POST"],
            status_code=status.HTTP_202_ACCEPTED,
            responses={status.HTTP_409_CONFLICT: {"description": "Re-score all is already running"}},
        )
        router.add_api_route("/status", self.rescore_status, methods=["GET"])
        router.add_api_route(
            "/locations",
            self.apply_locations,
            methods=["POST"],
            responses={status.HTTP_409_CONFLICT: {"description": "Re-score all is running"}},
        )
        router.add_api_route(
            "/{posting_id}",
            self.rescore_posting,
            methods=["POST"],
            responses={status.HTTP_404_NOT_FOUND: {"description": "No posting with this id"}},
        )
        return router

    async def start_rescore(self) -> RescoreStatus:
        """Apply the location rule to every stored posting, then begin scoring those not scored yet or still in New."""
        if not self._job.start():
            raise HTTPException(status.HTTP_409_CONFLICT, "Re-score all is already running")
        return self._job.status()

    def rescore_status(self) -> RescoreStatus:
        """Progress of the current or last Re-score all."""
        return self._job.status()

    def apply_locations(self) -> LocationSweepResult:
        """Apply the profile's location as it now stands to the stored postings, without scoring."""
        result = self._job.apply_locations()
        if result is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Re-score all is running; the new location applies when it is run again")
        return result

    async def rescore_posting(self, posting_id: int) -> Posting:
        """Apply the location rule to one posting and score it unless that archived it."""
        posting = await self._job.rescore_one(posting_id)
        if posting is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"posting {posting_id} not found")
        return posting
