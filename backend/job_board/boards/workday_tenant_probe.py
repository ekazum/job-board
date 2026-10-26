"""Find a company's Workday job site from its name when no careers page links one."""

import asyncio
import logging
import re

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.config.company_seed import CompanySeed
from job_board.enums.platform import Platform
from job_board.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

WD_HOSTS = tuple(f"wd{number}" for number in range(1, 13))
# "Sitemap: https://acme.wd5.myworkdayjobs.com/External/siteMap.xml", "Allow: /External/", "Disallow: /Private/"
SITEMAP_SITE = re.compile(r"^Sitemap:\s*https://[^/\s]+/([^/\s]+)/", re.IGNORECASE | re.MULTILINE)
RULE_SITE = re.compile(r"^(?:Allow|Disallow):\s*/([^/\s]+)/", re.IGNORECASE | re.MULTILINE)
NOT_SITES = frozenset({"refreshfacet"})


class WorkdayTenantProbe:
    """Tries the company name ("Check Point" -> "checkpoint") and the domain stem as a Workday tenant on
    wd1..wd12.myworkdayjobs.com.

    GET https://{tenant}.{host}.myworkdayjobs.com/robots.txt answers 200 only on the host the tenant lives on (422
    elsewhere, 401 for a tenant with no public site, and some hosts do not resolve), and its Sitemap/Allow/Disallow
    lines name the tenant's job sites. Each site, Sitemap ones first, is checked with the Workday source's probe; the
    first that answers with jobs is the board. Requests that fail count as misses, so this never raises.
    """

    def __init__(self, http: HttpClient, workday: BoardSource) -> None:
        self._http = http
        self._workday = workday

    async def find(self, seed: CompanySeed, stem: str) -> BoardRef | None:
        """The first tenant, host and site that serve jobs, or None."""
        tenants = list(dict.fromkeys(name for name in (re.sub(r"[^a-z0-9]", "", seed.name.lower()), stem) if name))
        candidates = [(tenant, host) for tenant in tenants for host in WD_HOSTS]
        robots = await asyncio.gather(*(self._robots(tenant, host) for tenant, host in candidates))
        for (tenant, host), text in zip(candidates, robots, strict=True):
            for site in self._sites(text or ""):
                board = BoardRef(Platform.WORKDAY, f"{tenant}/{site}", tenant=tenant, wd_host=host, site=site)
                if await self._serves_jobs(board):
                    logger.info("%s: Workday site found by probing %s.%s", seed.name, tenant, host)
                    return board
        return None

    async def _robots(self, tenant: str, host: str) -> str | None:
        """robots.txt of the tenant on this host, or None when the tenant does not live there."""
        response = await self._http.get(f"https://{tenant}.{host}.myworkdayjobs.com/robots.txt")
        return response.text if response.status == 200 else None

    async def _serves_jobs(self, board: BoardRef) -> bool:
        """The site's jobs endpoint answers; an unreachable site counts as no."""
        try:
            return await self._workday.probe(board)
        except BoardUnavailableError as error:
            logger.info("workday %s on %s: %s", board.slug, board.wd_host, error)
            return False

    @staticmethod
    def _sites(robots: str) -> list[str]:
        """Job-site names in robots.txt, Sitemap entries first, without duplicates or Workday's own paths."""
        sites = [*SITEMAP_SITE.findall(robots), *RULE_SITE.findall(robots)]
        return [site for site in dict.fromkeys(sites) if site.lower() not in NOT_SITES]
