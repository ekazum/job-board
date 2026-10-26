"""HttpClient: one retry on timeout/5xx, no retry otherwise, a shared concurrency limit."""

import asyncio

import httpx
import pytest

from job_board.utils.http_client import HttpClient

from tests.http_fakes import FakeWeb

URL = "https://acme.com/careers"


@pytest.mark.anyio
async def test_5xx_is_retried_once_then_succeeds() -> None:
    answers = iter([httpx.Response(503), httpx.Response(200, text="ok")])
    web = FakeWeb()
    web.route("GET", URL, lambda request: next(answers))
    async with web.client() as http:
        response = await http.get(URL)
    assert (response.status, response.text, len(web.requests)) == (200, "ok", 2)


@pytest.mark.anyio
async def test_timeout_is_retried_once_then_reported() -> None:
    web = FakeWeb()
    web.timeout(URL)
    async with web.client() as http:
        response = await http.get(URL)
    assert (response.status, response.timed_out, len(web.requests)) == (0, True, 2)
    assert response.error is not None and "timeout" in response.error


@pytest.mark.anyio
async def test_404_and_connection_errors_are_not_retried() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    web = FakeWeb()
    web.route("GET", "https://down.example/", refuse)
    async with web.client() as http:
        missing = await http.get(URL)
        down = await http.get("https://down.example/")
    assert (missing.status, down.status, len(web.requests)) == (404, 0, 2)
    assert down.error is not None and down.error.startswith("ConnectError")


@pytest.mark.anyio
async def test_redirects_are_followed_and_final_url_reported() -> None:
    web = FakeWeb()
    web.redirect(URL, "https://jobs.lever.co/acme")
    web.page("https://jobs.lever.co/acme", "<html>board</html>")
    async with web.client() as http:
        response = await http.get(URL)
    assert (response.status, response.url) == (200, "https://jobs.lever.co/acme")


@pytest.mark.anyio
async def test_post_json_sends_the_body_and_asks_for_json() -> None:
    web = FakeWeb()
    web.json("https://api.example/jobs", {"ok": True}, method="POST")
    async with web.client() as http:
        await http.post_json("https://api.example/jobs", {"searchText": "llm"})
    request = web.requests[0]
    assert (request.method, request.content, request.headers["accept"]) == ("POST", b'{"searchText":"llm"}', "application/json")


@pytest.mark.anyio
async def test_get_sends_extra_headers() -> None:
    web = FakeWeb()
    web.json("https://acme.careers.hibob.com/api/job-ad", {"ok": True})
    async with web.client() as http:
        await http.get("https://acme.careers.hibob.com/api/job-ad", {"companyIdentifier": "acme"})
    assert web.requests[0].headers["companyidentifier"] == "acme"


@pytest.mark.anyio
async def test_post_form_sends_url_encoded_fields_and_extra_headers() -> None:
    web = FakeWeb()
    web.json("https://api.example/graphql", {"ok": True}, method="POST")
    async with web.client() as http:
        await http.post_form("https://api.example/graphql", {"lsd": "TOKEN", "variables": '{"q": "ml"}'}, {"x-fb-lsd": "TOKEN"})
    request = web.requests[0]
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert (request.content, request.headers["x-fb-lsd"]) == (b"lsd=TOKEN&variables=%7B%22q%22%3A+%22ml%22%7D", "TOKEN")


@pytest.mark.anyio
async def test_at_most_max_concurrency_requests_in_flight() -> None:
    in_flight = peak = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, request=request)

    async with HttpClient(max_concurrency=3, transport=httpx.MockTransport(slow)) as http:
        await asyncio.gather(*(http.get(f"https://acme.com/{index}") for index in range(12)))
    assert peak == 3
