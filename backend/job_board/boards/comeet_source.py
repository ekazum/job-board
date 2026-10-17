"""Comeet: the careers API for widget boards, the hosted careers page otherwise."""

import json
import re
from urllib.parse import quote

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

API_ROOT = "https://www.comeet.co/careers-api/2.0/company"
POSITIONS_MARKER = "COMPANY_POSITIONS_DATA"
# A hosted page first declares the variable (`var COMPANY_POSITIONS_DATA ;`) and assigns it later, so anchor on
# the assignment itself; the first mention of the name is followed by unrelated arrays.
POSITIONS_ASSIGNMENT = re.compile(rf"\b{POSITIONS_MARKER}\s*=\s*(?=\[)")


class ComeetSource(BoardSource):
    """Reads Comeet positions; external_id is the position uid, text the concatenated details sections.

    With company_uid and token (found in the careers-page widget):
    GET careers-api/2.0/company/{uid}/positions?token={token}&details=true.
    Without a token (a comeet.com/jobs/{company}/{uid} or {x}.comeet.co link): the hosted page, which embeds
    every position as `COMPANY_POSITIONS_DATA = [...]`; a 200 page without that assignment is not a board.
    """

    @property
    def platform(self) -> Platform:
        """Comeet."""
        return Platform.COMEET

    @property
    def source(self) -> Source:
        """Comeet."""
        return Source.COMEET

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Public positions; internal ones are skipped."""
        if board.company_uid and board.token:
            positions = await self._api_positions(board.company_uid, board.token)
            fallback_url = f"https://www.comeet.com/jobs/{board.slug}"
        else:
            fallback_url = self._page_url(board.slug)
            positions = await self._page_positions(fallback_url)
        if positions is None:
            return None
        listings = (self._listing(fallback_url, position) for position in dicts(positions))
        return [listing for listing in listings if listing is not None]

    async def _api_positions(self, company_uid: str, token: str) -> list[object] | None:
        """Positions from the careers API."""
        url = f"{API_ROOT}/{quote(company_uid)}/positions?token={quote(token)}&details=true"
        return as_list(await self._get_json(url))

    async def _page_positions(self, page_url: str) -> list[object] | None:
        """Positions embedded in the hosted careers page."""
        response = await self._get(page_url)
        return None if response is None else self._embedded_positions(response.text, page_url)

    @staticmethod
    def _page_url(slug: str) -> str:
        """"acme/98.008" -> comeet.com/jobs/acme/98.008; "acme" -> acme.comeet.co."""
        return f"https://www.comeet.com/jobs/{slug}" if "/" in slug else f"https://{slug}.comeet.co/"

    @staticmethod
    def _embedded_positions(page: str, page_url: str) -> list[object] | None:
        """Decode the array assigned to COMPANY_POSITIONS_DATA; None when the page does not assign one."""
        assignment = POSITIONS_ASSIGNMENT.search(page)
        if assignment is None:
            return None
        try:
            decoded, _ = json.JSONDecoder().raw_decode(page, assignment.end())
        except json.JSONDecodeError as error:
            raise BoardUnavailableError(f"comeet {page_url}: {POSITIONS_MARKER} is not valid JSON ({error.msg})") from error
        positions: object = decoded
        return as_list(positions)

    @staticmethod
    def _listing(fallback_url: str, position: dict[str, object]) -> JobListing | None:
        """One position. The API names its sections "details"; the hosted page nests them in custom_fields."""
        uid = as_id(position.get("uid"))
        title = as_str(position.get("name")).strip()
        if not (uid and title) or position.get("is_internal") is True:
            return None
        url = as_str(position.get("url_comeet_hosted_page")) or as_str(position.get("url_active_page")) or fallback_url
        sections = dicts(position.get("details")) or dicts((as_dict(position.get("custom_fields")) or {}).get("details"))
        parts: list[str] = []
        for section in sections:
            parts.append(as_str(section.get("name")))
            parts.append(HtmlTextParser.to_text(as_str(section.get("value"))))
        text = "\n\n".join(part.strip() for part in parts if part.strip())
        return JobListing(external_id=uid, title=title, url=url, text=text)
