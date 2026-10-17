"""HTTP endpoints under /api/postings."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from job_board.enums.source import Source
from job_board.location_rule import LocationRule
from job_board.models.posting import Posting
from job_board.models.posting_facets import PostingFacets
from job_board.models.posting_create import PostingCreate
from job_board.models.posting_patch import PostingPatch
from job_board.models.purge_result import PurgeResult
from job_board.posting_filter import PostingFilter
from job_board.posting_repository import PostingRepository
from job_board.url_normalizer import UrlNormalizer


class PostingRoutes:
    """List, paste, update postings, and purge the location rule's rejects."""

    def __init__(self, repository: PostingRepository, normalizer: UrlNormalizer | None = None) -> None:
        self._repository = repository
        self._normalizer = normalizer or UrlNormalizer()

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/postings", tags=["postings"])
        router.add_api_route("", self.list_postings, methods=["GET"])
        router.add_api_route("/facets", self.posting_facets, methods=["GET"])
        router.add_api_route(
            "",
            self.create_posting,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            responses={status.HTTP_200_OK: {"model": Posting, "description": "Already on the board; returned unchanged"}},
        )
        router.add_api_route("/location-rejects", self.purge_location_rejects, methods=["DELETE"])
        router.add_api_route(
            "/{posting_id}",
            self.patch_posting,
            methods=["PATCH"],
            responses={status.HTTP_404_NOT_FOUND: {"description": "No posting with this id"}},
        )
        return router

    def list_postings(
        self,
        q: Annotated[str | None, Query(description="Case-insensitive substring of the title")] = None,
        company: Annotated[list[str] | None, Query(description="Only these companies (repeatable)")] = None,
        source: Annotated[list[Source] | None, Query(description="Only these sources (repeatable)")] = None,
        min_fit: Annotated[int | None, Query(ge=0, le=10, description="Fit at least this; unscored postings always pass")] = None,
        in_text: Annotated[bool, Query(description="Match q in the description too")] = False,
        location: Annotated[str | None, Query(description="Substring of the location; spellings normalized")] = None,
        archived: Annotated[
            bool, Query(description="The Archive: postings the scorer or the location rule closed as not relevant")
        ] = False,
    ) -> list[Posting]:
        """Postings matching the filter bar, newest first; without parameters, all of them."""
        posting_filter = PostingFilter(
            text=q or "",
            in_text=in_text,
            companies=tuple(company or ()),
            sources=tuple(source or ()),
            min_fit=min_fit,
            location=location or "",
            archived=archived,
        )
        return self._repository.search(posting_filter)

    def posting_facets(self) -> PostingFacets:
        """Companies and sources for the filter bar, and each column's unfiltered total."""
        return self._repository.facets()

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
            is_remote=LocationRule.is_remote(location="", title=body.title, text=body.text),
        )  # no location given, so no country: the location rule only decides scanned jobs
        if not created:
            response.status_code = status.HTTP_200_OK
        return posting

    def purge_location_rejects(self) -> PurgeResult:
        """Delete for good the postings the location rule archived (a later scan finds them again if still listed)."""
        return PurgeResult(deleted=self._repository.delete_location_rejects())

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
