"""Find which careers platform each company uses: `python -m job_board.runs.discover`."""

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import replace

from job_board.boards.board_link_finder import BoardLinkFinder
from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.careers_site_finder import CareersSiteFinder
from job_board.boards.default_sources import default_sources
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.boards.posting_company_finder import PostingCompanyFinder
from job_board.boards.workday_tenant_probe import WorkdayTenantProbe
from job_board.config.app_config import AppConfig
from job_board.config.company_seed import CompanySeed
from job_board.config.paths import CONFIG_PATH
from job_board.enums.platform import Platform
from job_board.models.discover_summary import DiscoverSummary
from job_board.storage.company_repository import CompanyRepository
from job_board.storage.database import Database
from job_board.utils.domains import domain_stem, same_company
from job_board.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

CAREER_PATHS = ("/careers", "/jobs", "/join-us")
# Comeet is absent: its boards need a company uid a domain cannot give. Workday has its own probe (WorkdayTenantProbe).
STEM_PROBE_ORDER = (Platform.GREENHOUSE, Platform.LEVER, Platform.ASHBY)


class Discover:
    """Orchestrates discovery for every company in config.yaml, plus stored companies with a domain or a careers URL
    (config.yaml wins when both list the same name). Companies run concurrently; HttpClient caps the requests.

    First, the companies of pasted postings that are not in the list are added (enabled), with the board or the
    domain their links give (PostingCompanyFinder), so the list grows with the companies you paste jobs from. One
    whose domain or board a listed company already has is that company under another name, and is left out.

    For each company:
    1. Google, Microsoft, Apple, Amazon and Meta get their own careers site, known from the domain or careers URL;
    2. otherwise fetch careers_url (config, else the stored one) and /careers, /jobs, /join-us at once, and take the
       board linked from the first of them, in that order, that links one; the board is verified against its API.
       A careers_url that is itself a board's link names that board even when the page does not load;
    3. otherwise probe the domain stem ("acme" for acme.com) on the Greenhouse, Lever and Ashby APIs;
    4. otherwise probe the name and the stem as a Workday tenant on wd1..wd12.myworkdayjobs.com;
    5. otherwise record platform=none. A company without a domain stops after step 2.

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
        posting_companies: PostingCompanyFinder | None = None,
    ) -> None:
        self._config = config
        self._database = database or Database(config.db_path)
        self._repository = repository or CompanyRepository(self._database)
        self._http = http
        self._link_finder = link_finder or BoardLinkFinder()
        self._sources = sources
        self._careers_sites = careers_sites or CareersSiteFinder()
        self._posting_companies = posting_companies or PostingCompanyFinder(self._link_finder)

    async def run(self) -> DiscoverSummary:
        """Add the pasted postings' companies, discover every company, save the results, and return how many
        succeeded, failed and were added."""
        started = time.monotonic()
        self._database.initialize()
        added = self._add_posting_companies()
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
        duration_s = round(time.monotonic() - started, 1)
        return DiscoverSummary(ok=len(seeds) - failed, failed=failed, duration_s=duration_s, added=added)

    def _add_posting_companies(self) -> int:
        """Put the companies of pasted postings that are not in the list on it; how many were added."""
        links: dict[str, tuple[str, list[str]]] = {}
        for company, url in self._repository.list_posting_companies():
            links.setdefault(company.casefold(), (company, []))[1].append(url)
        domains: set[str] = set()
        boards: set[tuple[Platform | None, str]] = set()
        for listed in self._repository.list_all():
            if listed.domain:
                domains.add(listed.domain)
            if listed.slug:
                boards.add((listed.platform, listed.slug.casefold()))
        added = 0
        for name, urls in links.values():
            seed, board = self._posting_companies.find(name, urls)
            board_key = None if board is None else (board.platform, board.slug.casefold())
            if seed.domain in domains or board_key in boards:
                logger.info("%s: not added, a listed company has its %s", name, "domain" if seed.domain else "board")
                continue
            _, created = self._repository.insert(seed.name, seed.domain, seed.careers_url)
            added += int(created)
            domains.update([seed.domain] if seed.domain else [])
            boards.update([board_key] if board_key else [])
            logger.info("%s: added from a pasted posting, domain %s, careers URL %s", name, seed.domain, seed.careers_url)
        return added

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
        if linked is not None:
            page_url, board = linked
            source = sources.get(board.platform)
            verified = source is not None and await source.probe(board)
            return DiscoveryFinding(board=board, verified=verified, careers_url=seed.careers_url or page_url)
        if seed.domain is None:
            return DiscoveryFinding(board=None, verified=False, careers_url=seed.careers_url)
        stem = domain_stem(seed.domain)
        finding = await self._probe_stem(seed, stem, sources)
        workday = sources.get(Platform.WORKDAY)
        if finding.board is not None or workday is None:
            return finding
        board = await WorkdayTenantProbe(http, workday).find(seed, stem)
        return finding if board is None else DiscoveryFinding(board=board, verified=True, careers_url=seed.careers_url)

    async def _linked_board(self, seed: CompanySeed, http: HttpClient) -> tuple[str, BoardRef] | None:
        """The board linked from the first candidate page, in priority order. The URL asked for counts too: a board URL
        that redirects to the company's own site (a Greenhouse board with a custom page) is still found, and so is one
        whose page does not load (a pasted job that has closed); of a page that does not load, only the URL counts."""
        pages = self._career_pages(seed)
        responses = await asyncio.gather(*(http.get(url) for url in pages))
        for page_url, response in zip(pages, responses, strict=True):
            loaded = response.status == 200
            board = self._link_finder.find(f"{response.url}\n{page_url}\n{response.text}" if loaded else page_url)
            if board is not None:
                return (response.url if loaded else page_url), board
        return None

    async def _probe_stem(
        self, seed: CompanySeed, stem: str, sources: Mapping[Platform, BoardSource]
    ) -> DiscoveryFinding:
        """Try the domain stem ("acme" for acme.co.il) as a slug on each probe platform at once; the first platform in
        STEM_PROBE_ORDER that has the board wins. Raises when none has it and any could not be reached.

        A guessed slug can belong to another company (greenhouse/orca is "ORCA Service Technologies", not
        Orca Security), so where the platform exposes a board name it must match the company name.
        """
        probes = [(platform, sources[platform]) for platform in STEM_PROBE_ORDER if platform in sources]
        results = await asyncio.gather(*(self._probe(source, BoardRef(platform, stem)) for platform, source in probes))
        for (platform, source), result in zip(probes, results, strict=True):
            if result is not True:
                continue
            board = BoardRef(platform, stem)
            board_name = await source.board_name(board)
            if board_name is not None and not same_company(seed.name, board_name):
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
        """careers_url first when known, then the standard paths on the company domain (when it has one)."""
        pages = [seed.careers_url] if seed.careers_url else []
        standard = [f"https://{seed.domain}{path}" for path in CAREER_PATHS] if seed.domain else []
        return pages + [page for page in standard if page not in pages]


def main() -> None:
    """Discover every company and print the summary as JSON."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = asyncio.run(Discover(AppConfig.from_yaml(CONFIG_PATH)).run())
    print(json.dumps(summary.model_dump(mode="json"), indent=2))  # ASCII-only, safe on a cp1255/cp1252 console


if __name__ == "__main__":
    main()
