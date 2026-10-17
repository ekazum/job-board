"""HTTP endpoints under /api/companies."""

from fastapi import APIRouter, HTTPException, Response, status

from job_board.company_repository import CompanyRepository
from job_board.models.company import Company
from job_board.models.company_create import CompanyCreate
from job_board.models.company_patch import CompanyPatch


class CompanyRoutes:
    """List, add and enable/disable companies."""

    def __init__(self, repository: CompanyRepository) -> None:
        self._repository = repository

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/companies", tags=["companies"])
        router.add_api_route("", self.list_companies, methods=["GET"])
        router.add_api_route(
            "",
            self.create_company,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            responses={status.HTTP_200_OK: {"model": Company, "description": "Already in the list; returned unchanged"}},
        )
        router.add_api_route(
            "/{company_id}",
            self.patch_company,
            methods=["PATCH"],
            responses={status.HTTP_404_NOT_FOUND: {"description": "No company with this id"}},
        )
        return router

    def list_companies(self) -> list[Company]:
        """All companies, alphabetically."""
        return self._repository.list_all()

    def create_company(self, body: CompanyCreate, response: Response) -> Company:
        """Add a company (name, optional domain); Discover fills in the rest. 201 when added, 200 when the name
        exists (any case), in which case the stored row is returned unchanged."""
        company, created = self._repository.insert(body.name, body.domain)
        if not created:
            response.status_code = status.HTTP_200_OK
        return company

    def patch_company(self, company_id: int, body: CompanyPatch) -> Company:
        """Enable or disable scanning for a company."""
        company = (
            self._repository.get(company_id)
            if body.enabled is None
            else self._repository.set_enabled(company_id, body.enabled)
        )
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"company {company_id} not found")
        return company
