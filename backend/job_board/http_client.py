"""Thin wrapper over requests so discovery and scanning can be tested without the network."""

import logging

import requests

from job_board.http_response import HttpResponse

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "job-board/0.1 (personal job tracker)"


class HttpClient:
    """GETs URLs with a timeout and User-Agent; network failures become status 0 instead of exceptions."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def get(self, url: str) -> HttpResponse:
        """GET a URL, following redirects."""
        try:
            response = self._session.get(url, timeout=self._timeout_seconds)
        except requests.RequestException as error:
            logger.info("GET %s failed: %s", url, error)
            return HttpResponse(url=url, status=0, text="", error=f"{type(error).__name__}: {error}")
        logger.debug("GET %s -> %s", url, response.status_code)
        return HttpResponse(url=response.url, status=response.status_code, text=response.text)
