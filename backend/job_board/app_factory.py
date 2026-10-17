"""Builds the FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from job_board.app_config import AppConfig
from job_board.company_repository import CompanyRepository
from job_board.company_routes import CompanyRoutes
from job_board.database import Database
from job_board.discover import Discover
from job_board.http_client import HttpClient
from job_board.posting_repository import PostingRepository
from job_board.posting_routes import PostingRoutes
from job_board.run_routes import RunRoutes
from job_board.scan import Scan

logger = logging.getLogger(__name__)


class AppFactory:
    """Assembles the FastAPI app: database lifecycle, API routes, and the built frontend.

    config_loader is called once here (for the database path) and again for every discover/scan run,
    so keyword and company edits in config.yaml take effect without restarting the server.
    """

    def __init__(
        self,
        config_loader: Callable[[], AppConfig],
        frontend_dist: Path,
        database: Database | None = None,
        http: HttpClient | None = None,
        posting_routes: PostingRoutes | None = None,
        company_routes: CompanyRoutes | None = None,
        run_routes: RunRoutes | None = None,
    ) -> None:
        self._config_loader = config_loader
        self._frontend_dist = frontend_dist
        self._database = database or Database(config_loader().db_path)
        self._http = http or HttpClient()
        self._posting_routes = posting_routes or PostingRoutes(PostingRepository(self._database))
        self._company_routes = company_routes or CompanyRoutes(CompanyRepository(self._database))
        self._run_routes = run_routes or RunRoutes(self._new_discover, self._new_scan)

    def build(self) -> FastAPI:
        """Create the app. API routers are added before the frontend mount, which catches every other path."""
        app = FastAPI(title="job-board", lifespan=self._lifespan, generate_unique_id_function=self._operation_id)
        app.include_router(self._posting_routes.router())
        app.include_router(self._company_routes.router())
        app.include_router(self._run_routes.router())
        self._mount_frontend(app)
        return app

    def _new_discover(self) -> Discover:
        """A discover run over the current config.yaml, sharing this app's database and HTTP session."""
        return Discover(self._config_loader(), database=self._database, http=self._http)

    def _new_scan(self) -> Scan:
        """A scan run over the current config.yaml, sharing this app's database and HTTP session."""
        return Scan(self._config_loader(), database=self._database, http=self._http)

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI) -> AsyncIterator[None]:
        """Initialize the database before the app starts serving requests."""
        self._database.initialize()
        yield

    def _mount_frontend(self, app: FastAPI) -> None:
        """Serve frontend/dist at / when it has been built; otherwise run API-only."""
        if not (self._frontend_dist / "index.html").is_file():
            logger.warning("No frontend build at %s; run `npm --prefix frontend run build`", self._frontend_dist)
            return
        app.mount("/", StaticFiles(directory=self._frontend_dist, html=True), name="frontend")

    @staticmethod
    def _operation_id(route: APIRoute) -> str:
        """Use the endpoint method name (list_postings, run_scan, ...) as the OpenAPI operationId."""
        return route.name
