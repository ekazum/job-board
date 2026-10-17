"""HTTP endpoints for the candidate profile."""

import re
from pathlib import Path, PurePath

from fastapi import APIRouter, HTTPException, UploadFile, status

from job_board.document_text import DocumentText
from job_board.models.profile import Profile
from job_board.models.profile_patch import ProfilePatch
from job_board.profile_repository import ProfileRepository

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^\w.\- ]")


class ProfileRoutes:
    """POST /api/profile (upload a .pdf, .docx, .md or .txt CV, max 5 MB: the text is extracted into the profile and
    the original kept in storage_dir), GET /api/profile, PATCH /api/profile (edit the text, targets and location;
    POST /api/rescore/locations then applies a new location to the stored postings)."""

    def __init__(self, repository: ProfileRepository, storage_dir: Path) -> None:
        self._repository = repository
        self._storage_dir = storage_dir

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/profile", tags=["profile"])
        router.add_api_route("", self.get_profile, methods=["GET"])
        router.add_api_route(
            "",
            self.upload_profile,
            methods=["POST"],
            responses={
                status.HTTP_413_CONTENT_TOO_LARGE: {"description": "File larger than 5 MB"},
                status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Unsupported or unreadable file"},
            },
        )
        router.add_api_route("", self.patch_profile, methods=["PATCH"])
        return router

    def get_profile(self) -> Profile:
        """The profile (blank, with no location, until you upload a CV or edit it)."""
        return self._repository.get() or Profile()

    async def upload_profile(self, file: UploadFile) -> Profile:
        """Extract the CV's text into the profile (targets and location are kept) and store the original file."""
        filename = self._safe_filename(file.filename or "cv.txt")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "the file is larger than 5 MB")
        try:
            text = DocumentText.extract(filename, data)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        if not text:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no text found in the file (a scanned PDF?)")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        (self._storage_dir / filename).write_bytes(data)
        return self._repository.save_upload(text, filename)

    def patch_profile(self, body: ProfilePatch) -> Profile:
        """Edit the extracted text, the targets, the location and/or allow_fully_remote."""
        return self._repository.update(body)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """The base name only, with characters outside letters, digits, ".", "-", "_" and space replaced."""
        base = PurePath(name.replace("\\", "/")).name.strip() or "cv.txt"
        return UNSAFE_FILENAME_CHARACTERS.sub("_", base)
