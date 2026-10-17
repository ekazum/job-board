"""Google careers (google.com/about/careers), read through the search call its results page makes."""

import asyncio
import json

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.boards.keyword_search_source import KeywordSearchSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.html_text_parser import HtmlTextParser
from job_board.utils.json_values import as_id, as_list, as_str

RPC_ID = "r06xKb"
SEARCH_URL = f"https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute?rpcids={RPC_ID}"
JOB_URL = "https://www.google.com/about/careers/applications/jobs/results/{}"
RESPONSE_PREFIX = ")]}'"
MAX_PAGES_PER_TERM = 25
# Positions in a job array of the search result.
ID, TITLE, RESPONSIBILITIES, QUALIFICATIONS, LOCATIONS, ABOUT = 0, 1, 3, 4, 9, 10


class GoogleSource(KeywordSearchSource):
    """Searches Google's careers site once per wanted role, restricted to the configured locations.

    POST {SEARCH_URL} with the form field f.req = [[["r06xKb", args, null, "generic"]]], where args is the JSON text
    [[query, null, null, null, "en-US", null, [[location], ...], page]]. The answer is ")]}'" and a JSON list of
    envelopes; the ["wrb.fr", "r06xKb", result] one carries result as JSON text: [jobs, null, total, page_size].
    A job is an array: 0 id, 1 title, 3 [_, responsibilities HTML], 4 [_, qualifications HTML],
    9 [[location name, ...], ...], 10 [_, about HTML]. Descriptions come with the results, so no detail requests.
    The board's slug is "google".
    """

    @property
    def platform(self) -> Platform:
        """Google."""
        return Platform.GOOGLE

    @property
    def source(self) -> Source:
        """Google."""
        return Source.GOOGLE

    async def probe(self, board: BoardRef) -> bool:
        """The search answers."""
        del board  # one site, whatever the slug
        return await self._search_page("", 1) is not None

    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """Jobs found by any role search, in a configured location, with descriptions; None if the search is gone."""
        del board
        per_term = await asyncio.gather(*(self._search_all(term) for term in self._search_terms))
        if all(jobs is None for jobs in per_term):
            return None
        listings: dict[str, JobListing] = {}
        for jobs in per_term:
            for job in jobs or []:
                listing = self._listing(job)
                if listing is not None and self._wanted(listing.title) and self._in_location(listing.location):
                    listings.setdefault(listing.external_id, listing)
        return list(listings.values())

    async def _search_all(self, term: str) -> list[list[object]] | None:
        """Every result for one term, page by page; None when the search endpoint does not exist."""
        jobs: list[list[object]] = []
        for page in range(1, MAX_PAGES_PER_TERM + 1):
            result = await self._search_page(term, page)
            if result is None:
                return None if page == 1 else jobs
            batch, total = result
            jobs.extend(batch)
            if not batch or len(jobs) >= total:
                break
        return jobs

    async def _search_page(self, term: str, page: int) -> tuple[list[list[object]], int] | None:
        """One page of jobs and the total count; None on 404."""
        locations = [[location] for location in self._locations] or None
        args = json.dumps([[term, None, None, None, "en-US", None, locations, page]])
        response = await self._post_form(SEARCH_URL, {"f.req": json.dumps([[[RPC_ID, args, None, "generic"]]])})
        if response is None:
            return None
        result = as_list(self._parsed(SEARCH_URL, self._rpc_result(response.text))) or []
        jobs = [job for job in (as_list(item) for item in as_list(self._at(result, 0)) or []) if job is not None]
        total = self._at(result, 2)
        return jobs, total if isinstance(total, int) else len(jobs)

    def _rpc_result(self, text: str) -> str:
        """The result JSON text inside the ["wrb.fr", "r06xKb", result] envelope."""
        envelopes = as_list(self._parsed(SEARCH_URL, text.removeprefix(RESPONSE_PREFIX))) or []
        for envelope in (as_list(item) or [] for item in envelopes):
            if envelope[:2] == ["wrb.fr", RPC_ID] and isinstance(self._at(envelope, 2), str):
                return as_str(envelope[2])
        raise BoardUnavailableError(f"google {SEARCH_URL}: no {RPC_ID} result in the answer")

    def _listing(self, job: list[object]) -> JobListing | None:
        """One job from its array; None without an id or title."""
        external_id = as_id(self._at(job, ID))
        title = as_str(self._at(job, TITLE)).strip()
        if not (external_id and title):
            return None
        sections = (self._html(job, ABOUT), self._html(job, RESPONSIBILITIES), self._html(job, QUALIFICATIONS))
        places = [as_str(self._at(as_list(place) or [], 0)) for place in as_list(self._at(job, LOCATIONS)) or []]
        return JobListing(
            external_id=external_id,
            title=title,
            url=JOB_URL.format(external_id),
            text="\n\n".join(HtmlTextParser.to_text(section) for section in sections if section),
            location=" | ".join(place for place in places if place),
        )

    def _html(self, job: list[object], index: int) -> str:
        """The HTML of a [null, html] field."""
        return as_str(self._at(as_list(self._at(job, index)) or [], 1))

    @staticmethod
    def _at(values: list[object], index: int) -> object:
        """values[index], or None when the array is shorter."""
        return values[index] if index < len(values) else None
