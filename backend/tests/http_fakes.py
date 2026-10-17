"""Canned HTTP responses for tests that must not touch the network."""

import json
from collections.abc import Mapping
from unittest.mock import MagicMock

from job_board.http_client import HttpClient
from job_board.http_response import HttpResponse


def json_response(url: str, payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(url=url, status=status, text=json.dumps(payload))


def page(url: str, html: str, final_url: str | None = None) -> HttpResponse:
    """A 200 HTML page; final_url simulates a redirect."""
    return HttpResponse(url=final_url or url, status=200, text=html)


def failure(url: str, status: int = 0) -> HttpResponse:
    """status 0 = no response (DNS/timeout); otherwise an HTTP error status."""
    return HttpResponse(url=url, status=status, text="", error="ConnectionError: offline" if status == 0 else None)


def fake_http(responses: Mapping[str, HttpResponse]) -> MagicMock:
    """An HttpClient whose get() serves the given URLs and answers 404 for everything else."""
    def serve(url: str) -> HttpResponse:
        return responses.get(url, HttpResponse(url=url, status=404, text="Not Found"))

    http = MagicMock(spec=HttpClient)
    http.get.side_effect = serve
    return http


def requested_urls(http: MagicMock) -> list[str]:
    return [call.args[0] for call in http.get.call_args_list]
