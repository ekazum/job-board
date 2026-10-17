"""Serve recorded responses to the real HttpClient through httpx.MockTransport; no test touches the network."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from job_board.http_client import HttpClient
from job_board.utils.json_values import as_dict, as_list

FIXTURES = Path(__file__).parent / "fixtures"
Handler = Callable[[httpx.Request], httpx.Response]


def fixture_text(name: str) -> str:
    """A recorded response body from tests/fixtures (trimmed real API answers)."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> object:
    """A recorded JSON response from tests/fixtures."""
    data: object = json.loads(fixture_text(name))
    return data


def fixture_dict(name: str) -> dict[str, object]:
    """A recorded JSON object."""
    data = as_dict(fixture_json(name))
    if data is None:
        raise ValueError(f"{name} is not a JSON object")
    return data


def fixture_list(name: str) -> list[object]:
    """A recorded JSON array."""
    data = as_list(fixture_json(name))
    if data is None:
        raise ValueError(f"{name} is not a JSON array")
    return data


class FakeWeb:
    """Answers (method, url) pairs it was told about and 404 for everything else; records every request."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], Handler] = {}
        self.requests: list[httpx.Request] = []

    def route(self, method: str, url: str, handler: Handler) -> None:
        """Answer method + url with a custom handler (e.g. one that reads the JSON body)."""
        self._routes[(method, url)] = handler

    def page(self, url: str, html: str, status: int = 200) -> None:
        """An HTML page."""
        self.route("GET", url, lambda request: httpx.Response(status, text=html, request=request))

    def json(self, url: str, payload: object, status: int = 200, method: str = "GET") -> None:
        """A JSON answer."""
        self.route(method, url, lambda request: httpx.Response(status, json=payload, request=request))

    def fixture(self, url: str, name: str, method: str = "GET") -> None:
        """A recorded JSON answer from tests/fixtures."""
        self.json(url, fixture_json(name), method=method)

    def redirect(self, url: str, location: str) -> None:
        """A 302 to another URL (which must be routed too)."""
        self.route("GET", url, lambda request: httpx.Response(302, headers={"Location": location}, request=request))

    def status(self, url: str, status: int, method: str = "GET") -> None:
        """An empty answer with the given status (e.g. 503)."""
        self.route(method, url, lambda request: httpx.Response(status, text="", request=request))

    def timeout(self, url: str, method: str = "GET") -> None:
        """No answer: the request times out."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        self.route(method, url, handler)

    def client(self, max_concurrency: int = 10) -> HttpClient:
        """The app's HttpClient wired to this fake."""
        return HttpClient(max_concurrency=max_concurrency, transport=httpx.MockTransport(self._handle))

    def urls(self, method: str | None = None) -> list[str]:
        """URLs requested so far, in order (optionally only one method)."""
        return [str(request.url) for request in self.requests if method is None or request.method == method]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self._routes.get((request.method, str(request.url)))
        return httpx.Response(404, text="Not Found", request=request) if handler is None else handler(request)
