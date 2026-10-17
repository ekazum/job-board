"""Read the boards of verified companies, score the new jobs and add them as cards: `python -m job_board.scan`."""

import asyncio
import json
import logging
import os
import time
from collections.abc import Mapping

from dotenv import load_dotenv

from job_board.app_config import AppConfig
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.default_sources import default_sources
from job_board.boards.job_listing import JobListing
from job_board.boards.scan_target import ScanTarget
from job_board.company_repository import CompanyRepository
from job_board.database import Database
from job_board.enums.outcome import Outcome
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.fit_result import FitResult
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter
from job_board.location_resolver import LocationResolver
from job_board.location_rule import LocationRule
from job_board.models.run_summary import RunSummary
from job_board.paths import CONFIG_PATH, ENV_PATH
from job_board.posting_repository import PostingRepository
from job_board.profile_repository import ProfileRepository
from job_board.scorer import Scorer
from job_board.triage import Triage

logger = logging.getLogger(__name__)


class Scan:
    """Orchestrates a scan: read every verified + enabled company's board concurrently, keep jobs whose title
    matches a wanted role (keywords.include) and no excluded one (keywords.exclude), and skip jobs already stored.
    A new job outside the profile's location (LocationRule) is not stored at all, and costs no LLM call (a later scan
    looks at it again, so it arrives once the location allows it); the rest are scored against the profile and
    inserted with status new when fit >= llm.threshold or the job could not be scored, otherwise closed as
    not_relevant.

    Inserts skip existing (source, external_id) rows, so a rescan never duplicates a card, resets its status or
    scores it again; it only fills in the location of a stored job that has none. A board that cannot be read
    records its error in companies.last_error and the scan carries on; a board read successfully clears it. Workday
    sites and the single-company careers sites (Google, Microsoft, Apple, Amazon, Meta) are searched for the include
    keywords and narrowed to config.locations on the way in; that only saves requests, the profile's locations
    decide.
    """

    def __init__(
        self,
        config: AppConfig,
        database: Database | None = None,
        companies: CompanyRepository | None = None,
        postings: PostingRepository | None = None,
        http: HttpClient | None = None,
        sources: Mapping[Platform, BoardSource] | None = None,
        keyword_filter: KeywordFilter | None = None,
        scorer: Scorer | None = None,
        environ: Mapping[str, str] | None = None,
        location_rule: LocationRule | None = None,
    ) -> None:
        self._config = config
        self._database = database or Database(config.db_path)
        self._companies = companies or CompanyRepository(self._database)
        self._postings = postings or PostingRepository(self._database)
        self._http = http
        self._sources = sources
        self._filter = keyword_filter or KeywordFilter(config.include_keywords, config.exclude_keywords)
        self._scorer = scorer
        self._environ = os.environ if environ is None else environ
        self._triage = Triage(config.llm.threshold)
        self._location_rule = location_rule  # None: the stored profile's, read when the scan starts

    async def run(self) -> RunSummary:
        """Scan every verified, enabled company and return how many boards were read and how many failed."""
        started = time.monotonic()
        self._database.initialize()
        location_rule = self._location_rule or LocationRule.for_profile(ProfileRepository(self._database).get())
        targets = self._companies.list_scannable()
        if self._http is None:
            async with HttpClient() as http:
                results = await self._fetch_all(targets, http)
        else:
            results = await self._fetch_all(targets, self._http)
        failed = 0
        fresh: list[tuple[ScanTarget, JobListing]] = []
        for target, result in zip(targets, results, strict=True):
            if isinstance(result, str):
                failed += 1
                self._companies.set_last_error(target.company, result)
                logger.warning("%s: %s", target.company, result)
                continue
            source = Source(target.board.platform)
            kept = [job for job in result if self._filter.matches(job.title)]
            stored = [job for job in kept if self._postings.exists(source, job.external_id)]
            new = [job for job in kept if job not in stored]
            self._postings.fill_locations(
                source, ((job.external_id, job.location, self._is_remote(job), self._country(job)) for job in stored)
            )
            fresh.extend((target, job) for job in new)
            self._companies.set_last_error(target.company, None)
            logger.info("%s: %d jobs, %d matched, %d new", target.company, len(result), len(kept), len(new))
        await self._score_and_insert(fresh, location_rule)
        return RunSummary(ok=len(targets) - failed, failed=failed, duration_s=round(time.monotonic() - started, 1))

    async def _fetch_all(self, targets: list[ScanTarget], http: HttpClient) -> list[list[JobListing] | str]:
        """Every board at once; each result is its jobs or the error that stopped it."""
        sources = self._sources or default_sources(http, self._filter, self._config.locations)
        return list(await asyncio.gather(*(self._fetch(target, sources) for target in targets)))

    @staticmethod
    async def _fetch(target: ScanTarget, sources: Mapping[Platform, BoardSource]) -> list[JobListing] | str:
        """One board's jobs, or why they could not be read."""
        source = sources.get(target.board.platform)
        if source is None:
            return f"no reader for {target.board.platform}"
        try:
            jobs = await source.fetch_jobs(target.board)
        except BoardUnavailableError as error:
            return str(error)
        if jobs is None:
            return f"{target.board.platform} board '{target.board.slug}' no longer exists; run Discover again"
        return jobs

    async def _score_and_insert(self, fresh: list[tuple[ScanTarget, JobListing]], location_rule: LocationRule) -> None:
        """Drop the new jobs outside the profile's location, score the others (the LLM client caps how many at once)
        and insert each with its triage."""
        wanted = [
            (target, job)
            for target, job in fresh
            if location_rule.rejection(country=self._country(job), location=job.location, title=job.title, text=job.text) is None
        ]
        if len(wanted) < len(fresh):
            logger.info("%d new jobs outside your location were not stored", len(fresh) - len(wanted))
        if not wanted:
            return
        scorer = self._scorer or Scorer.from_settings(self._config.llm, ProfileRepository(self._database), self._environ)
        try:
            fits = await asyncio.gather(
                *(scorer.score(title=job.title, company=target.company, location=job.location, text=job.text) for target, job in wanted)
            )
        finally:
            if self._scorer is None:
                await scorer.aclose()
        archived = 0
        for (target, job), fit in zip(wanted, fits, strict=True):
            status, outcome = self._triage.decide(fit.fit)
            self._insert(target, job, fit, status, outcome)
            archived += outcome is not None
        logger.info("scored %d new jobs: %d to New, %d to the Archive", len(wanted), len(wanted) - archived, archived)

    def _insert(self, target: ScanTarget, job: JobListing, fit: FitResult, status: Status, outcome: Outcome | None) -> None:
        """Add one new job with its fit and where it goes."""
        self._postings.insert(
            source=Source(target.board.platform),
            external_id=job.external_id,
            company=target.company,
            title=job.title,
            url=job.url,
            text=job.text,
            location=job.location,
            is_remote=self._is_remote(job),
            country=self._country(job),
            status=status,
            outcome=outcome,
            fit=fit,
        )

    @staticmethod
    def _is_remote(job: JobListing) -> bool:
        """What LocationRule.is_remote says about the job."""
        return LocationRule.is_remote(location=job.location, title=job.title, text=job.text)

    @staticmethod
    def _country(job: JobListing) -> str | None:
        """The job's country from the board's own field, else from its location text."""
        return LocationResolver.shared().resolve(job.location, job.country)


def main() -> None:
    """Scan every verified, enabled company and print the summary as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(ENV_PATH)
    summary = asyncio.run(Scan(AppConfig.from_yaml(CONFIG_PATH)).run())
    print(json.dumps(summary.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
