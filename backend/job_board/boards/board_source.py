"""Base class for reading one platform's public job boards."""

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping

from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.utils.http_client import HttpClient
from job_board.utils.http_response import HttpResponse

NOT_FOUND_STATUSES = frozenset({404, 410})


class BoardSource(ABC):
    """Reads job boards on one platform.

    Contract for every method that takes a board: a list (possibly empty) means the board exists, None means
    there is no such board, and BoardUnavailableError means the answer is unknown (network, 5xx, 429, bad body).
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """The platform this source reads."""

    @property
    @abstractmethod
    def source(self) -> Source:
        """The postings.source value for jobs read by this source."""

    @abstractmethod
    async def fetch_jobs(self, board: BoardRef) -> list[JobListing] | None:
        """All public jobs on the board, with plain-text descriptions."""

    async def probe(self, board: BoardRef) -> bool:
        """True when the board exists. Sources override this with a lighter request where the API allows."""
        return await self.fetch_jobs(board) is not None

    async def board_name(self, board: BoardRef) -> str | None:
        """The company name the platform shows for this board, or None when the API does not expose one.
        Used to reject a guessed slug that belongs to a different company."""
        del board  # most platforms' public APIs carry no board name
        return None

    async def _get(self, url: str, headers: Mapping[str, str] | None = None) -> HttpResponse | None:
        """GET a board URL: the response on 200, None on 404/410, BoardUnavailableError otherwise."""
        return self._checked(url, await self._http.get(url, headers))

    async def _get_json(self, url: str, headers: Mapping[str, str] | None = None) -> object | None:
        """GET and decode a JSON body; None on 404/410."""
        response = await self._get(url, headers)
        return None if response is None else self._decoded(url, response)

    async def _post_json(self, url: str, payload: object) -> object | None:
        """POST a JSON body and decode the JSON answer; None on 404/410."""
        response = self._checked(url, await self._http.post_json(url, payload))
        return None if response is None else self._decoded(url, response)

    async def _post_form(self, url: str, fields: Mapping[str, str], headers: Mapping[str, str] | None = None) -> HttpResponse | None:
        """POST form fields: the response on 200, None on 404/410, BoardUnavailableError otherwise."""
        return self._checked(url, await self._http.post_form(url, fields, headers))

    def _checked(self, url: str, response: HttpResponse) -> HttpResponse | None:
        """The response on 200, None on 404/410, BoardUnavailableError for anything else."""
        if response.status in NOT_FOUND_STATUSES:
            return None
        if response.status != 200:
            reason = response.error or f"HTTP {response.status}"
            raise BoardUnavailableError(f"{self.platform} {url}: {reason}")
        return response

    def _decoded(self, url: str, response: HttpResponse) -> object:
        """The JSON body; BoardUnavailableError when it is not JSON."""
        return self._parsed(url, response.text)

    def _parsed(self, url: str, text: str) -> object:
        """JSON text from url decoded; BoardUnavailableError when it is not JSON."""
        try:
            data: object = json.loads(text)
        except json.JSONDecodeError as error:
            raise BoardUnavailableError(f"{self.platform} {url}: body is not JSON ({error.msg})") from error
        return data
