"""Read the boards of verified companies and add matching jobs as new cards: `python -m job_board.scan`."""

import asyncio
import json
import logging
import time
from collections.abc import Mapping

from job_board.app_config import AppConfig
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.default_sources import default_sources
from job_board.boards.job_listing import JobListing
from job_board.boards.scan_target import ScanTarget
from job_board.company_repository import CompanyRepository
from job_board.database import Database
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter
from job_board.models.run_summary import RunSummary
from job_board.paths import CONFIG_PATH
from job_board.posting_repository import PostingRepository

logger = logging.getLogger(__name__)


class Scan:
    """Orchestrates a scan: read every verified + enabled company's board concurrently, keep jobs whose title
    matches a wanted role (keywords.include) and no excluded one (keywords.exclude), and insert them as status new.

    Inserts skip existing (source, external_id) rows, so a rescan never duplicates a card or resets its status.
    A board that cannot be read records its error in companies.last_error and the scan carries on; a board read
    successfully clears it. Workday sites are searched for the include keywords and filtered to
    config.workday_locations.
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
    ) -> None:
        self._config = config
        self._database = database or Database(config.db_path)
        self._companies = companies or CompanyRepository(self._database)
        self._postings = postings or PostingRepository(self._database)
        self._http = http
        self._sources = sources
        self._filter = keyword_filter or KeywordFilter(config.include_keywords, config.exclude_keywords)

    async def run(self) -> RunSummary:
        """Scan every verified, enabled company and return how many boards were read and how many failed."""
        started = time.monotonic()
        self._database.initialize()
        targets = self._companies.list_scannable()
        if self._http is None:
            async with HttpClient() as http:
                results = await self._fetch_all(targets, http)
        else:
            results = await self._fetch_all(targets, self._http)
        failed = 0
        for target, result in zip(targets, results, strict=True):
            if isinstance(result, str):
                failed += 1
                self._companies.set_last_error(target.company, result)
                logger.warning("%s: %s", target.company, result)
                continue
            kept = [job for job in result if self._filter.matches(job.title)]
            added = sum(self._insert(target, job) for job in kept)
            self._companies.set_last_error(target.company, None)
            logger.info("%s: %d jobs, %d matched, %d new", target.company, len(result), len(kept), added)
        return RunSummary(ok=len(targets) - failed, failed=failed, duration_s=round(time.monotonic() - started, 1))

    async def _fetch_all(self, targets: list[ScanTarget], http: HttpClient) -> list[list[JobListing] | str]:
        """Every board at once; each result is its jobs or the error that stopped it."""
        sources = self._sources or default_sources(http, self._filter, self._config.workday_locations)
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

    def _insert(self, target: ScanTarget, job: JobListing) -> bool:
        """Add one job as a new card; False when it was already on the board."""
        _, created = self._postings.insert(
            source=Source(target.board.platform),
            external_id=job.external_id,
            company=target.company,
            title=job.title,
            url=job.url,
            text=job.text,
        )
        return created


def main() -> None:
    """Scan every verified, enabled company and print the summary as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = asyncio.run(Scan(AppConfig.from_yaml(CONFIG_PATH)).run())
    print(json.dumps(summary.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
