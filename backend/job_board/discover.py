"""Find which careers platform each company uses: `python -m job_board.discover`."""

import asyncio
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import replace

from job_board.app_config import AppConfig
from job_board.boards.board_link_finder import BoardLinkFinder
from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.careers_site_finder import CareersSiteFinder
from job_board.boards.default_sources import default_sources
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.boards.workday_tenant_probe import WorkdayTenantProbe
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.enums.platform import Platform
from job_board.http_client import HttpClient
from job_board.models.run_summary import RunSummary
from job_board.paths import CONFIG_PATH

logger = logging.getLogger(__name__)

CAREER_PATHS = ("/careers", "/jobs", "/join-us")
# Comeet is absent: its boards need a company uid a domain cannot give. Workday has its own probe (WorkdayTenantProbe).
STEM_PROBE_ORDER = (Platform.GREENHOUSE, Platform.LEVER, Platform.ASHBY)
# Second-level labels of two-part public suffixes: acme.co.il -> "acme", not "co".
SECOND_LEVEL_LABELS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


class Discover:
    """Orchestrates discovery for every company in config.yaml, plus companies added in the UI with a domain
    (config.yaml wins when both list the same name). Companies run concurrently; HttpClient caps the requests.

    For each company:
    1. Google, Microsoft, Apple, Amazon and Meta get their own careers site, known from the domain or careers URL;
    2. otherwise fetch careers_url (config, else the stored one) and /careers, /jobs, /join-us at once, and take the
       board linked from the first of them, in that order, that links one; the board is verified against its API;
    3. otherwise probe the domain stem ("acme" for acme.com) on the Greenhouse, Lever and Ashby APIs;
    4. otherwise probe the name and the stem as a Workday tenant on wd1..wd12.myworkdayjobs.com;
    5. otherwise record platform=none.

    A company whose boards could not be reached keeps what an earlier run found; the error goes to last_error.
    """

    def __init__(
        self,
        config: AppConfig,
        database: Database | None = None,
        repository: CompanyRepository | None = None,
        http: HttpClient | None = None,
        link_finder: BoardLinkFinder | None = None,
        sources: Mapping[Platform, BoardSource] | None = None,
        careers_sites: CareersSiteFinder | None = None,
    ) -> None:
        self._config = config
        self._database = database or Database(config.db_path)
        self._repository = repository or CompanyRepository(self._database)
        self._http = http
        self._link_finder = link_finder or BoardLinkFinder()
        self._sources = sources
        self._careers_sites = careers_sites or CareersSiteFinder()

    async def run(self) -> RunSummary:
        """Discover every company, save the results, and return how many succeeded and failed."""
        started = time.monotonic()
        self._database.initialize()
        seeds = self._seeds()
        if self._http is None:
            async with HttpClient() as http:
                outcomes = await self._discover_all(seeds, http)
        else:
            outcomes = await self._discover_all(seeds, self._http)
        failed = 0
        for seed, outcome in zip(seeds, outcomes, strict=True):
            if isinstance(outcome, DiscoveryFinding):
                self._repository.record_discovery(seed, outcome)
                self._log_finding(seed, outcome)
            else:
                failed += 1
                self._repository.record_failure(seed, outcome)
                logger.warning("%s: %s", seed.name, outcome)
        return RunSummary(ok=len(seeds) - failed, failed=failed, duration_s=round(time.monotonic() - started, 1))

    def _seeds(self) -> list[CompanySeed]:
        """config.yaml companies (filling a missing careers_url from the stored row), then stored companies with a
        domain that config.yaml does not list."""
        stored = {seed.name.casefold(): seed for seed in self._repository.list_seeds()}
        seeds: list[CompanySeed] = []
        for configured in self._config.companies:
            previous = stored.pop(configured.name.casefold(), None)
            if configured.careers_url is None and previous is not None and previous.careers_url:
                seeds.append(replace(configured, careers_url=previous.careers_url))
            else:
                seeds.append(configured)
        return seeds + list(stored.values())

    async def _discover_all(self, seeds: list[CompanySeed], http: HttpClient) -> list[DiscoveryFinding | str]:
        """Every company at once; each result is a finding or the error that stopped it."""
        sources = self._sources or default_sources(http)
        return list(await asyncio.gather(*(self._discover_or_error(seed, http, sources) for seed in seeds)))

    async def _discover_or_error(
        self, seed: CompanySeed, http: HttpClient, sources: Mapping[Platform, BoardSource]
    ) -> DiscoveryFinding | str:
        """One company's finding, or its error message."""
        try:
            return await self._discover(seed, http, sources)
        except BoardUnavailableError as error:
            return str(error)

    async def _discover(self, seed: CompanySeed, http: HttpClient, sources: Mapping[Platform, BoardSource]) -> DiscoveryFinding:
        """Own careers site, careers-page link, domain-stem probe, Workday tenant probe, in that order."""
        own = self._careers_sites.find(seed)
        if own is not None:
            source = sources.get(own.platform)
            verified = source is not None and await source.probe(own)
            return DiscoveryFinding(board=own, verified=verified, careers_url=seed.careers_url)
        linked = await self._linked_board(seed, http)
        if linked is None:
            finding = await self._probe_stem(seed, sources)
            workday = sources.get(Platform.WORKDAY)
            if finding.board is not None or workday is None:
                return finding
            board = await WorkdayTenantProbe(http, workday).find(seed, self._domain_stem(seed.domain))
            return finding if board is None else DiscoveryFinding(board=board, verified=True, careers_url=seed.careers_url)
        page_url, board = linked
        source = sources.get(board.platform)
        verified = source is not None and await source.probe(board)
        return DiscoveryFinding(board=board, verified=verified, careers_url=seed.careers_url or page_url)

    async def _linked_board(self, seed: CompanySeed, http: HttpClient) -> tuple[str, BoardRef] | None:
        """The board linked from the first candidate page, in priority order; pages that fail are skipped."""
        responses = await asyncio.gather(*(http.get(url) for url in self._career_pages(seed)))
        for response in responses:
            if response.status != 200:
                continue
            board = self._link_finder.find(f"{response.url}\n{response.text}")
            if board is not None:
                return response.url, board
        return None

    async def _probe_stem(self, seed: CompanySeed, sources: Mapping[Platform, BoardSource]) -> DiscoveryFinding:
        """Try the domain stem as a slug on each probe platform at once; the first platform in STEM_PROBE_ORDER
        that has the board wins. Raises when none has it and any could not be reached.

        A guessed slug can belong to another company (greenhouse/orca is "ORCA Service Technologies", not
        Orca Security), so where the platform exposes a board name it must match the company name.
        """
        stem = self._domain_stem(seed.domain)
        probes = [(platform, sources[platform]) for platform in STEM_PROBE_ORDER if platform in sources]
        results = await asyncio.gather(*(self._probe(source, BoardRef(platform, stem)) for platform, source in probes))
        for (platform, source), result in zip(probes, results, strict=True):
            if result is not True:
                continue
            board = BoardRef(platform, stem)
            board_name = await source.board_name(board)
            if board_name is not None and not self._same_company(seed.name, board_name):
                logger.info("%s: %s/%s skipped, it belongs to %r", seed.name, platform, stem, board_name)
                continue
            return DiscoveryFinding(board=board, verified=True, careers_url=seed.careers_url)
        failures = [result for result in results if isinstance(result, str)]
        if failures:
            raise BoardUnavailableError("; ".join(failures))
        return DiscoveryFinding(board=None, verified=False, careers_url=seed.careers_url)

    @staticmethod
    async def _probe(source: BoardSource, board: BoardRef) -> bool | str:
        """Whether the board exists, or the error that prevented finding out."""
        try:
            return await source.probe(board)
        except BoardUnavailableError as error:
            return str(error)

    @staticmethod
    def _log_finding(seed: CompanySeed, finding: DiscoveryFinding) -> None:
        """One line per company."""
        if finding.board is None:
            logger.info("%s: no supported platform", seed.name)
        else:
            state = "verified" if finding.verified else "NOT verified"
            logger.info("%s: %s/%s, %s", seed.name, finding.board.platform, finding.board.slug, state)

    @staticmethod
    def _career_pages(seed: CompanySeed) -> list[str]:
        """careers_url first when known, then the standard paths on the company domain."""
        pages = [seed.careers_url] if seed.careers_url else []
        return pages + [f"https://{seed.domain}{path}" for path in CAREER_PATHS if f"https://{seed.domain}{path}" not in pages]

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
    """Discover every company and print the summary as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = asyncio.run(Discover(AppConfig.from_yaml(CONFIG_PATH)).run())
    print(json.dumps(summary.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
