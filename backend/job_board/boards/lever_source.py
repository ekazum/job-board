"""Lever postings API."""

from urllib.parse import quote

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

API_ROOT = "https://api.lever.co/v0/postings"


class LeverSource(BoardSource):
    """api.lever.co/v0/postings/{slug}?mode=json: a top-level JSON array; 404 for an unknown slug."""

    @property
    def platform(self) -> Platform:
        """Lever."""
        return Platform.LEVER

    @property
    def source(self) -> Source:
        """Lever."""
        return Source.LEVER

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """All postings with plain-text descriptions."""
        postings = as_list(await self._get_json(f"{API_ROOT}/{quote(board.slug)}?mode=json"))
        if postings is None:
            return None
        listings = (self._listing(posting) for posting in dicts(postings))
        return [listing for listing in listings if listing is not None]

    async def probe(self, board: BoardRef) -> bool:
        """Board exists: one posting is enough (limit=1)."""
        return as_list(await self._get_json(f"{API_ROOT}/{quote(board.slug)}?mode=json&limit=1")) is not None

    @staticmethod
    def _listing(posting: dict[str, object]) -> JobListing | None:
        """One posting: title is "text"; description = descriptionPlain + each list (heading + items) + additionalPlain."""
        external_id = as_id(posting.get("id"))
        title = as_str(posting.get("text")).strip()
        url = as_str(posting.get("hostedUrl"))
        if not (external_id and title and url):
            return None
        parts = [as_str(posting.get("descriptionPlain")) or HtmlTextParser.to_text(as_str(posting.get("description")))]
        for section in dicts(posting.get("lists")):
            parts.append(as_str(section.get("text")))
            parts.append(HtmlTextParser.to_text(as_str(section.get("content"))))
        parts.append(as_str(posting.get("additionalPlain")))
        text = "\n\n".join(part.strip() for part in parts if part.strip())
        location = as_str((as_dict(posting.get("categories")) or {}).get("location"))
        return JobListing(external_id=external_id, title=title, url=url, text=text, location=location)
