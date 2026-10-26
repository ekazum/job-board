"""Careers sites built on the tyco-wp WordPress theme (jobs.iai.co.il), read from the jobs file their pages load."""

from urllib.parse import quote

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.json_values import as_id, as_list, as_str, dicts

JOBS_FILE = "/wp-content/themes/tyco-wp/assets/json/jobs.json"


class TycoSource(BoardSource):
    """GET https://{host}/wp-content/themes/tyco-wp/assets/json/jobs.json answers a list of every open job (no paging;
    the jobs page filters it in the browser). A job has id, tl (title), dc (the description, plain text), ct (the
    city, in the site's language: "יהוד") and more; its page is https://{host}/job/{id}/. The board's slug is the
    site's host ("jobs.iai.co.il"; BoardLinkFinder finds the file named in the jobs page as _jobsFile).
    """

    @property
    def platform(self) -> Platform:
        """Tyco."""
        return Platform.TYCO

    @property
    def source(self) -> Source:
        """Tyco."""
        return Source.TYCO

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Every job with its description; None when the site has no jobs file."""
        root = f"https://{quote(board.slug)}"
        jobs = as_list(await self._get_json(f"{root}{JOBS_FILE}"))
        if jobs is None:
            return None
        listings = (self._listing(root, job) for job in dicts(jobs))
        return [listing for listing in listings if listing is not None]

    @staticmethod
    def _listing(root: str, job: dict[str, object]) -> JobListing | None:
        """One job; its location is the city."""
        external_id = as_id(job.get("id"))
        title = as_str(job.get("tl")).strip()
        if not (external_id and title):
            return None
        return JobListing(
            external_id=external_id,
            title=title,
            url=f"{root}/job/{external_id}/",
            text=as_str(job.get("dc")).strip(),
            location=as_str(job.get("ct")).strip(),
        )
