"""Async HTTP for discovery and scanning: one connection pool, a concurrency limit, a timeout and one retry."""

import asyncio
import logging
from collections.abc import Mapping
from types import TracebackType
from typing import Self

import httpx

from job_board.http_response import HttpResponse

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_CONCURRENCY = 10
RETRIES = 1
DEFAULT_USER_AGENT = "job-board/0.1 (personal job tracker)"
JSON_HEADERS = {"Accept": "application/json"}


class HttpClient:
    """GET and POST through one httpx.AsyncClient, used as `async with HttpClient() as http`.

    At most max_concurrency requests are in flight across the whole run. A timeout or 5xx response is retried
    once; network failures become status 0 with error set, so callers never see transport exceptions.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            transport=transport,
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> Self:
        """Enter the client's lifetime."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        await self._client.aclose()

    async def get(self, url: str) -> HttpResponse:
        """GET a URL, following redirects."""
        return await self._send("GET", url)

    async def post_json(self, url: str, payload: object) -> HttpResponse:
        """POST a JSON body and ask for a JSON answer."""
        return await self._send("POST", url, payload=payload)

    async def post_form(self, url: str, fields: Mapping[str, str], headers: Mapping[str, str] | None = None) -> HttpResponse:
        """POST url-encoded form fields, with extra headers when the site asks for them (an anti-CSRF token)."""
        return await self._send("POST", url, form=fields, headers=headers)

    async def _send(
        self,
        method: str,
        url: str,
        *,
        payload: object = None,
        form: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """One attempt plus RETRIES more when the attempt timed out or the server answered 5xx."""
        attempt = 0
        while True:
            response = await self._attempt(method, url, payload, form, headers)
            if attempt >= RETRIES or not self._retryable(response):
                return response
            attempt += 1
            logger.info("%s %s: %s, retry %d", method, url, response.error or response.status, attempt)

    async def _attempt(
        self, method: str, url: str, payload: object, form: Mapping[str, str] | None, headers: Mapping[str, str] | None
    ) -> HttpResponse:
        """A single request inside the concurrency limit."""
        async with self._semaphore:
            try:
                if payload is not None:
                    response = await self._client.request(method, url, json=payload, headers=JSON_HEADERS)
                elif form is not None:
                    response = await self._client.request(method, url, data=dict(form), headers=dict(headers or {}))
                else:
                    response = await self._client.request(method, url)
            except httpx.TimeoutException as error:
                return HttpResponse(url=url, status=0, text="", error=f"timeout: {error!r}", timed_out=True)
            except httpx.HTTPError as error:
                return HttpResponse(url=url, status=0, text="", error=f"{type(error).__name__}: {error}")
        return HttpResponse(url=str(response.url), status=response.status_code, text=response.text)

    @staticmethod
    def _retryable(response: HttpResponse) -> bool:
        """Timeouts and server errors are worth one more try; 4xx and connection failures are not."""
        return response.timed_out or response.status >= 500
