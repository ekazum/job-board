"""Read the boards of verified companies and add matching jobs as new cards: `python -m job_board.scan`."""

import json
import logging
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
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter
from job_board.models.run_issue import RunIssue
from job_board.models.scan_result import ScanResult
from job_board.paths import CONFIG_PATH
from job_board.posting_repository import PostingRepository

logger = logging.getLogger(__name__)


class Scan:
    """Orchestrates a scan: for each verified + enabled company, fetch the board, keep jobs that pass the
    include/exclude keywords (title + text), and insert them as status new.

    Inserts skip existing (source, external_id) rows, so a rescan never duplicates a card or resets its
    status. ON CONFLICT DO NOTHING is used rather than INSERT OR IGNORE, which would also swallow CHECK
    violations. A board that cannot be read is reported as an issue and the scan carries on.
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
        self._database = database or Database(config.db_path)
        self._companies = companies or CompanyRepository(self._database)
        self._postings = postings or PostingRepository(self._database)
        self._sources = sources or default_sources(http or HttpClient())
        self._filter = keyword_filter or KeywordFilter(config.include_keywords, config.exclude_keywords)

    def run(self) -> ScanResult:
        """Scan every verified, enabled company and return the counts."""
        self._database.initialize()
        targets = self._companies.list_scannable()
        jobs_seen = matched = added = 0
        issues: list[RunIssue] = []
        for target in targets:
            source = self._sources.get(target.board.platform)
            if source is None:
                issues.append(RunIssue(company=target.company, message=f"no reader for {target.board.platform}"))
                continue
            try:
                jobs = source.fetch_jobs(target.board.slug)
            except BoardUnavailableError as error:
                logger.warning("%s: skipped, %s", target.company, error)
                issues.append(RunIssue(company=target.company, message=str(error)))
                continue
            if jobs is None:
                message = f"{target.board.platform} board '{target.board.slug}' no longer exists; run discover again"
                issues.append(RunIssue(company=target.company, message=message))
                continue
            kept = [job for job in jobs if self._filter.matches(job.title, job.text)]
            new = sum(self._insert(source, target, job) for job in kept)
            logger.info("%s: %d jobs, %d matched, %d new", target.company, len(jobs), len(kept), new)
            jobs_seen += len(jobs)
            matched += len(kept)
            added += new
        return ScanResult(companies=len(targets), jobs_seen=jobs_seen, matched=matched, added=added, issues=issues)

    def _insert(self, source: BoardSource, target: ScanTarget, job: JobListing) -> bool:
        """Add one job as a new card; False when it was already on the board."""
        _, created = self._postings.insert(
            source=source.source,
            external_id=job.external_id,
            company=target.company,
            title=job.title,
            url=job.url,
            text=job.text,
        )
        return created


def main() -> None:
    """Scan every verified, enabled company and print the counts as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = Scan(AppConfig.from_yaml(CONFIG_PATH)).run()
    print(json.dumps(result.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
