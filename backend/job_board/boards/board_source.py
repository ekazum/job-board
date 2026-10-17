"""Base class for reading one platform's public job boards."""

import json
from abc import ABC, abstractmethod

from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.job_listing import JobListing
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.http_client import HttpClient
from job_board.http_response import HttpResponse

NOT_FOUND_STATUSES = frozenset({404, 410})


class BoardSource(ABC):
    """Reads job boards on one platform.

    Contract for every method that takes a slug: a list (possibly empty) means the board exists, None means
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
    def fetch_jobs(self, slug: str) -> list[JobListing] | None:
        """All public jobs on the board, with plain-text descriptions."""

    def probe(self, slug: str) -> bool:
        """True when the board exists. Sources override this with a lighter request where the API allows."""
        return self.fetch_jobs(slug) is not None

    def board_name(self, slug: str) -> str | None:
        """The company name the platform shows for this board, or None when the API does not expose one.
        Used to reject a guessed slug that belongs to a different company."""
        del slug  # most platforms' public APIs carry no board name
        return None

    def _get(self, url: str) -> HttpResponse | None:
        """GET a board URL: the response on 200, None on 404/410, BoardUnavailableError otherwise."""
        response = self._http.get(url)
        if response.status in NOT_FOUND_STATUSES:
            return None
        if response.status != 200:
            reason = response.error or f"HTTP {response.status}"
            raise BoardUnavailableError(f"{self.platform} {url}: {reason}")
        return response

    def _get_json(self, url: str) -> object | None:
        """GET and decode a JSON body; None on 404/410."""
        response = self._get(url)
        if response is None:
            return None
        try:
            data: object = json.loads(response.text)
        except json.JSONDecodeError as error:
            raise BoardUnavailableError(f"{self.platform} {url}: body is not JSON ({error.msg})") from error
        return data
