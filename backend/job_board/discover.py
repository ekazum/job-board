"""Find which careers platform each company in config.yaml uses: `python -m job_board.discover`."""

import json
import logging
import re
from collections.abc import Mapping

from job_board.app_config import AppConfig
from job_board.boards.board_link_finder import BoardLinkFinder
from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.default_sources import default_sources
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.enums.platform import Platform
from job_board.http_client import HttpClient
from job_board.models.discover_result import DiscoverResult
from job_board.models.run_issue import RunIssue
from job_board.paths import CONFIG_PATH

logger = logging.getLogger(__name__)

CAREER_PATHS = ("/careers", "/jobs", "/join-us")
# Comeet is absent: its boards need a company uid, which cannot be guessed from a domain.
STEM_PROBE_ORDER = (Platform.GREENHOUSE, Platform.LEVER, Platform.ASHBY)
# Second-level labels of two-part public suffixes: acme.co.il -> "acme", not "co".
SECOND_LEVEL_LABELS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


class Discover:
    """Orchestrates discovery for every company in config.yaml, plus companies added in the UI with a
    domain (config.yaml wins when both list the same name):

    1. fetch careers_url (if configured), /careers, /jobs, /join-us and look for a board link;
       a link found is verified against that platform's public API;
    2. otherwise probe the domain stem ("acme" for acme.com) on the Greenhouse, Lever and Ashby APIs;
    3. otherwise record platform=none.

    Each company is upserted into the companies table. A company whose boards could not be reached
    (network, 5xx) is reported as an issue and its stored row is left unchanged.
    """

    def __init__(
        self,
        config: AppConfig,
        database: Database | None = None,
        repository: CompanyRepository | None = None,
        http: HttpClient | None = None,
        link_finder: BoardLinkFinder | None = None,
        sources: Mapping[Platform, BoardSource] | None = None,
    ) -> None:
        self._config = config
        self._database = database or Database(config.db_path)
        self._repository = repository or CompanyRepository(self._database)
        self._http = http or HttpClient()
        self._link_finder = link_finder or BoardLinkFinder()
        self._sources = sources or default_sources(self._http)

    def run(self) -> DiscoverResult:
        """Discover every company and return the counts."""
        self._database.initialize()
        seeds = self._seeds()
        verified = unverified = no_platform = 0
        issues: list[RunIssue] = []
        for seed in seeds:
            try:
                finding = self._discover(seed)
            except BoardUnavailableError as error:
                logger.warning("%s: skipped, %s", seed.name, error)
                issues.append(RunIssue(company=seed.name, message=str(error)))
                continue
            self._repository.record_discovery(seed, finding)
            if finding.board is None:
                logger.info("%s: no supported platform", seed.name)
            else:
                state = "verified" if finding.verified else "NOT verified"
                logger.info("%s: %s/%s, %s", seed.name, finding.board.platform, finding.board.slug, state)
            if finding.board is None:
                no_platform += 1
            elif finding.verified:
                verified += 1
            else:
                unverified += 1
        return DiscoverResult(
            companies=len(seeds),
            verified=verified,
            unverified=unverified,
            no_platform=no_platform,
            issues=issues,
        )

    def _seeds(self) -> list[CompanySeed]:
        """config.yaml companies, then stored companies with a domain that config.yaml does not list."""
        configured = list(self._config.companies)
        names = {seed.name.casefold() for seed in configured}
        added = [seed for seed in self._repository.list_seeds() if seed.name.casefold() not in names]
        return configured + added

    def _discover(self, seed: CompanySeed) -> DiscoveryFinding:
        """Careers-page link first, domain-stem probe second."""
        linked = self._linked_board(seed)
        if linked is None:
            return self._probe_stem(seed)
        page_url, board = linked
        source = self._sources.get(board.platform)
        verified = source is not None and source.probe(board.slug)
        return DiscoveryFinding(board=board, verified=verified, careers_url=page_url)

    def _linked_board(self, seed: CompanySeed) -> tuple[str, BoardRef] | None:
        """The first careers page (in order) that links a board, with that board.

        Pages that fail to load are skipped: most companies have only one of the standard paths.
        """
        for url in self._career_pages(seed):
            response = self._http.get(url)
            if response.status != 200:
                continue
            board = self._link_finder.find(f"{response.url}\n{response.text}")
            if board is not None:
                return response.url, board
        return None

    def _probe_stem(self, seed: CompanySeed) -> DiscoveryFinding:
        """Try the domain stem as a slug on each probe platform; raise if none answered and any failed.

        A guessed slug can belong to another company (greenhouse/orca is "ORCA Service Technologies", not
        Orca Security), so where the platform exposes a board name it must match the company name.
        """
        stem = self._domain_stem(seed.domain)
        failures: list[str] = []
        for platform in STEM_PROBE_ORDER:
            source = self._sources.get(platform)
            if source is None:
                continue
            try:
                if not source.probe(stem):
                    continue
            except BoardUnavailableError as error:
                failures.append(str(error))
                continue
            board_name = source.board_name(stem)
            if board_name is not None and not self._same_company(seed.name, board_name):
                logger.info("%s: %s/%s skipped, it belongs to %r", seed.name, platform, stem, board_name)
                continue
            return DiscoveryFinding(board=BoardRef(platform, stem), verified=True, careers_url=seed.careers_url)
        if failures:
            raise BoardUnavailableError("; ".join(failures))
        return DiscoveryFinding(board=None, verified=False, careers_url=seed.careers_url)

    @staticmethod
    def _career_pages(seed: CompanySeed) -> list[str]:
        """careers_url first when configured, then the standard paths on the company domain."""
        pages = [seed.careers_url] if seed.careers_url else []
        return pages + [f"https://{seed.domain}{path}" for path in CAREER_PATHS]

    @staticmethod
    def _same_company(company: str, board_name: str) -> bool:
        """Names match when one contains the other, ignoring case, spaces and punctuation:
        "Via" ~ "Via Transportation", "Melio" ~ "Melio Payments"; "Orca Security" !~ "ORCA Service Technologies"."""
        mine, theirs = (re.sub(r"[^a-z0-9]", "", name.lower()) for name in (company, board_name))
        return bool(mine) and bool(theirs) and (mine in theirs or theirs in mine)

    @staticmethod
    def _domain_stem(domain: str) -> str:
        """"acme.com" -> "acme", "acme.co.il" -> "acme", "careers.acme.io" -> "acme"."""
        labels = domain.lower().removeprefix("www.").split(".")
        if len(labels) >= 3 and labels[-2] in SECOND_LEVEL_LABELS and len(labels[-1]) == 2:
            return labels[-3]
        return labels[-2] if len(labels) >= 2 else labels[0]


def main() -> None:
    """Discover every company in config.yaml and print the counts as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = Discover(AppConfig.from_yaml(CONFIG_PATH)).run()
    print(json.dumps(result.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
