"""HiBob careers sites (<company>.careers.hibob.com), read through the API their pages call."""

from urllib.parse import quote

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_str, dicts

# The parts of a job ad, in the order the site shows them; each is HTML.
SECTIONS = ("description", "responsibilities", "requirements", "benefits")


class HibobSource(BoardSource):
    """GET https://{slug}.careers.hibob.com/api/job-ad with the header companyIdentifier: {slug} answers
    {"jobAdDetails": [...]} with every open job (no paging; 401 without the header). A job has id, title, country
    ("Israel"), workspaceType ("Hybrid", "Remote") and its sections as HTML. The board's slug is the site's subdomain
    ("hibob-fa0ad69d0cb34a").
    """

    @property
    def platform(self) -> Platform:
        """HiBob."""
        return Platform.HIBOB

    @property
    def source(self) -> Source:
        """HiBob."""
        return Source.HIBOB

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Every job with its sections as text; None when the site does not exist."""
        root = f"https://{quote(board.slug)}.careers.hibob.com"
        data = as_dict(await self._get_json(f"{root}/api/job-ad", headers={"companyIdentifier": board.slug}))
        if data is None:
            return None
        listings = (self._listing(root, job) for job in dicts(data.get("jobAdDetails")))
        return [listing for listing in listings if listing is not None]

    @staticmethod
    def _listing(root: str, job: dict[str, object]) -> JobListing | None:
        """One job; its location is the country, with ", Remote" for a remote one."""
        external_id = as_id(job.get("id"))
        title = as_str(job.get("title")).strip()
        if not (external_id and title):
            return None
        sections = (HtmlTextParser.to_text(as_str(job.get(section))) for section in SECTIONS)
        country = as_str(job.get("country")).strip()
        remote = as_str(job.get("workspaceType")).strip().lower() == "remote"
        return JobListing(
            external_id=external_id,
            title=title,
            url=f"{root}/jobs/{external_id}",
            text="\n\n".join(section for section in sections if section),
            location=", ".join(part for part in (country, "Remote" if remote else "") if part),
            country=country,
        )
