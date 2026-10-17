"""Ashby posting API."""

from urllib.parse import quote

from job_board.boards.board_source import BoardSource
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

API_ROOT = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(BoardSource):
    """api.ashbyhq.com/posting-api/job-board/{slug}: {"jobs": [...]}; 404 for an unknown slug."""

    @property
    def platform(self) -> Platform:
        """Ashby."""
        return Platform.ASHBY

    @property
    def source(self) -> Source:
        """Ashby."""
        return Source.ASHBY

    def fetch_jobs(self, slug: str) -> list[JobListing] | None:
        """All listed jobs (isListed false ones are skipped)."""
        data = as_dict(self._get_json(f"{API_ROOT}/{quote(slug)}"))
        jobs = None if data is None else as_list(data.get("jobs"))
        if jobs is None:
            return None
        listings = (self._listing(job) for job in dicts(jobs) if job.get("isListed") is not False)
        return [listing for listing in listings if listing is not None]

    @staticmethod
    def _listing(job: dict[str, object]) -> JobListing | None:
        """One job; descriptionPlain, falling back to the HTML description."""
        external_id = as_id(job.get("id"))
        title = as_str(job.get("title")).strip()
        url = as_str(job.get("jobUrl"))
        if not (external_id and title and url):
            return None
        text = as_str(job.get("descriptionPlain")) or HtmlTextParser.to_text(as_str(job.get("descriptionHtml")))
        return JobListing(external_id=external_id, title=title, url=url, text=text.strip())
