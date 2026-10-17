"""Greenhouse job board API."""

import html
from urllib.parse import quote

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

API_ROOT = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(BoardSource):
    """boards-api.greenhouse.io/v1/boards/{slug}/jobs: {"jobs": [...]}; 404 for an unknown slug."""

    @property
    def platform(self) -> Platform:
        """Greenhouse."""
        return Platform.GREENHOUSE

    @property
    def source(self) -> Source:
        """Greenhouse."""
        return Source.GREENHOUSE

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """All jobs with descriptions (content=true; several MB for large boards)."""
        jobs = await self._jobs_array(f"{API_ROOT}/{quote(board.slug)}/jobs?content=true")
        if jobs is None:
            return None
        listings = (self._listing(job) for job in dicts(jobs))
        return [listing for listing in listings if listing is not None]

    async def probe(self, board: BoardRef) -> bool:
        """Board exists: the same endpoint without content, about 20x smaller."""
        return await self._jobs_array(f"{API_ROOT}/{quote(board.slug)}/jobs") is not None

    async def board_name(self, board: BoardRef) -> str | None:
        """GET /v1/boards/{slug} -> {"name": "Acme", ...}; None when it cannot be read."""
        try:
            data = as_dict(await self._get_json(f"{API_ROOT}/{quote(board.slug)}"))
        except BoardUnavailableError:
            return None
        name = None if data is None else as_str(data.get("name")).strip()
        return name or None

    async def _jobs_array(self, url: str) -> list[object] | None:
        """The "jobs" array of a board response, or None when the board does not exist."""
        data = as_dict(await self._get_json(url))
        return None if data is None else as_list(data.get("jobs"))

    @staticmethod
    def _listing(job: dict[str, object]) -> JobListing | None:
        """One job; content is entity-encoded HTML ("&lt;p&gt;"), so it is unescaped before tag stripping."""
        external_id = as_id(job.get("id"))
        title = as_str(job.get("title")).strip()
        url = as_str(job.get("absolute_url"))
        if not (external_id and title and url):
            return None
        text = HtmlTextParser.to_text(html.unescape(as_str(job.get("content"))))
        location = as_str((as_dict(job.get("location")) or {}).get("name"))
        return JobListing(external_id=external_id, title=title, url=url, text=text, location=location)
