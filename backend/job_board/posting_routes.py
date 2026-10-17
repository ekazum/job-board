"""HTTP endpoints under /api/postings."""

from fastapi import APIRouter, HTTPException, Response, status

from job_board.enums.source import Source
from job_board.models.posting import Posting
from job_board.models.posting_create import PostingCreate
from job_board.models.posting_patch import PostingPatch
from job_board.posting_repository import PostingRepository
from job_board.url_normalizer import UrlNormalizer


class PostingRoutes:
    """List, paste and update postings."""

    def __init__(self, repository: PostingRepository, normalizer: UrlNormalizer | None = None) -> None:
        self._repository = repository
        self._normalizer = normalizer or UrlNormalizer()

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/postings", tags=["postings"])
        router.add_api_route("", self.list_postings, methods=["GET"])
        router.add_api_route(
            "",
            self.create_posting,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            responses={status.HTTP_200_OK: {"model": Posting, "description": "Already on the board; returned unchanged"}},
        )
        router.add_api_route(
            "/{posting_id}",
            self.patch_posting,
            methods=["PATCH"],
            responses={status.HTTP_404_NOT_FOUND: {"description": "No posting with this id"}},
        )
        return router

    def list_postings(self) -> list[Posting]:
        """All postings, newest first."""
        return self._repository.list_all()

    def create_posting(self, body: PostingCreate, response: Response) -> Posting:
        """Add a pasted posting (source manual, external_id = canonical URL). 201 when added, 200 when already there."""
        try:
            external_id = self._normalizer.normalize(body.url)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        posting, created = self._repository.insert(
            source=Source.MANUAL,
            external_id=external_id,
            company=body.company,
            title=body.title,
            url=body.url,
            text=body.text,
        )
        if not created:
            response.status_code = status.HTTP_200_OK
        return posting

    def patch_posting(self, posting_id: int, body: PostingPatch) -> Posting:
        """Change status, outcome and/or note. Leaving closed clears the outcome."""
        current = self._repository.get(posting_id)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"posting {posting_id} not found")
        try:
            updated = body.apply_to(current)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        saved = self._repository.save(updated)
        if saved is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"posting {posting_id} not found")
        return saved
