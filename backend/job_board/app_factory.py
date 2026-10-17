"""Builds the FastAPI application."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from job_board.app_config import AppConfig
from job_board.company_repository import CompanyRepository
from job_board.company_routes import CompanyRoutes
from job_board.config_editor import ConfigEditor
from job_board.database import Database
from job_board.discover import Discover
from job_board.location_rule import LocationRule
from job_board.location_sweep import LocationSweep
from job_board.paths import CONFIG_PATH
from job_board.posting_repository import PostingRepository
from job_board.posting_routes import PostingRoutes
from job_board.profile_repository import ProfileRepository
from job_board.profile_routes import ProfileRoutes
from job_board.rescore_job import RescoreJob
from job_board.rescore_routes import RescoreRoutes
from job_board.run_routes import RunRoutes
from job_board.scan import Scan
from job_board.scorer import Scorer
from job_board.settings_routes import SettingsRoutes

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
        posting_routes: PostingRoutes | None = None,
        company_routes: CompanyRoutes | None = None,
        run_routes: RunRoutes | None = None,
        settings_routes: SettingsRoutes | None = None,
        profile_routes: ProfileRoutes | None = None,
        rescore_routes: RescoreRoutes | None = None,
        config_path: Path = CONFIG_PATH,
    ) -> None:
        self._config_loader = config_loader
        self._frontend_dist = frontend_dist
        self._database = database or Database(config_loader().db_path)
        self._posting_routes = posting_routes or PostingRoutes(PostingRepository(self._database))
        self._company_routes = company_routes or CompanyRoutes(CompanyRepository(self._database))
        self._run_routes = run_routes or RunRoutes(self._new_discover, self._new_scan)
        self._settings_routes = settings_routes or SettingsRoutes(config_loader, ConfigEditor(config_path))
        self._profiles = ProfileRepository(self._database)
        self._profile_routes = profile_routes or ProfileRoutes(self._profiles, self._database.path.parent / "profile")
        postings = PostingRepository(self._database)
        rescore_job = RescoreJob(postings, self._new_scorer, self._threshold, LocationSweep(postings, self._location_rule))
        self._rescore_routes = rescore_routes or RescoreRoutes(rescore_job)

    def build(self) -> FastAPI:
        """Create the app. API routers are added before the frontend mount, which catches every other path."""
        app = FastAPI(title="job-board", lifespan=self._lifespan, generate_unique_id_function=self._operation_id)
        app.include_router(self._posting_routes.router())
        app.include_router(self._company_routes.router())
        app.include_router(self._run_routes.router())
        app.include_router(self._settings_routes.router())
        app.include_router(self._profile_routes.router())
        app.include_router(self._rescore_routes.router())
        self._mount_frontend(app)
        return app

    def _new_discover(self) -> Discover:
        """A discover run over the current config.yaml on this app's database (it opens its own HTTP client)."""
        return Discover(self._config_loader(), database=self._database)

    def _new_scorer(self) -> Scorer:
        """A scorer on the provider currently in config.yaml, reading this app's profile."""
        return Scorer.from_settings(self._config_loader().llm, self._profiles, os.environ)

    def _threshold(self) -> int:
        """llm.threshold as currently in config.yaml."""
        return self._config_loader().llm.threshold

    def _location_rule(self) -> LocationRule:
        """The location rule of the profile as currently stored."""
        return LocationRule.for_profile(self._profiles.get())

    def _new_scan(self) -> Scan:
        """A scan run over the current config.yaml on this app's database (it opens its own HTTP client)."""
        return Scan(self._config_loader(), database=self._database)

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
