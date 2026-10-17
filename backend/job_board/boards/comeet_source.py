"""Comeet hosted careers pages."""

import json
import re

from job_board.boards.board_source import BoardSource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_dict, as_id, as_list, as_str, dicts

POSITIONS_MARKER = "COMPANY_POSITIONS_DATA"
# The page first declares the variable (`var COMPANY_POSITIONS_DATA ;`) and assigns it later, so anchor on
# the assignment itself; the first mention of the name is followed by unrelated arrays.
POSITIONS_ASSIGNMENT = re.compile(rf"\b{POSITIONS_MARKER}\s*=\s*(?=\[)")


class ComeetSource(BoardSource):
    """Comeet has no public API keyed by slug; its hosted page (comeet.com/jobs/{slug}/{uid}) embeds every
    position as `COMPANY_POSITIONS_DATA = [...]`, which is decoded here. A 200 page without that variable
    is not a Comeet board."""

    @property
    def platform(self) -> Platform:
        """Comeet."""
        return Platform.COMEET

    @property
    def source(self) -> Source:
        """Comeet."""
        return Source.COMEET

    def fetch_jobs(self, slug: str) -> list[JobListing] | None:
        """All public positions; internal ones are skipped. external_id is "{slug}:{position uid}"."""
        page_url = self._page_url(slug)
        response = self._get(page_url)
        if response is None:
            return None
        positions = self._positions(response.text, page_url)
        if positions is None:
            return None
        listings = (self._listing(slug, page_url, position) for position in dicts(positions))
        return [listing for listing in listings if listing is not None]

    @staticmethod
    def _page_url(slug: str) -> str:
        """"acme/98.008" -> comeet.com/jobs/acme/98.008; "acme" -> acme.comeet.co."""
        return f"https://www.comeet.com/jobs/{slug}" if "/" in slug else f"https://{slug}.comeet.co/"

    @staticmethod
    def _positions(page: str, page_url: str) -> list[object] | None:
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
    def _listing(slug: str, page_url: str, position: dict[str, object]) -> JobListing | None:
        """One position; the description is the concatenated custom_fields.details sections."""
        uid = as_id(position.get("uid"))
        title = as_str(position.get("name")).strip()
        if not (uid and title) or position.get("is_internal") is True:
            return None
        url = as_str(position.get("url_comeet_hosted_page")) or as_str(position.get("url_active_page")) or page_url
        parts: list[str] = []
        custom_fields = as_dict(position.get("custom_fields")) or {}
        for section in dicts(custom_fields.get("details")):
            parts.append(as_str(section.get("name")))
            parts.append(HtmlTextParser.to_text(as_str(section.get("value"))))
        text = "\n\n".join(part.strip() for part in parts if part.strip())
        return JobListing(external_id=f"{slug}:{uid}", title=title, url=url, text=text)
