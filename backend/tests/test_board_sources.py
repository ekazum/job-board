"""Board sources against canned responses shaped like the live APIs (checked 2026-10-17)."""

import html

import pytest

from job_board.boards.ashby_source import AshbySource
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.comeet_source import ComeetSource
from job_board.boards.greenhouse_source import GreenhouseSource
from job_board.boards.job_listing import JobListing
from job_board.boards.lever_source import LeverSource
from job_board.http_response import HttpResponse

from tests.http_fakes import failure, fake_http, json_response, page, requested_urls

GH_JOBS = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
GH_FULL = f"{GH_JOBS}?content=true"
LEVER = "https://api.lever.co/v0/postings/acme?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/acme"
COMEET = "https://www.comeet.com/jobs/acme/98.008"


# --- Greenhouse -------------------------------------------------------------------------------------------


def test_greenhouse_jobs_with_entity_encoded_content() -> None:
    content = html.escape("<h2>About</h2><p>APIs &amp; data.</p>")
    payload = {
        "jobs": [
            {"id": 4461450008, "title": " Backend Engineer ", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1", "content": content},
            {"id": 2, "title": "", "absolute_url": "https://x"},  # no title: skipped
        ],
        "meta": {"total": 2},
    }
    jobs = GreenhouseSource(fake_http({GH_FULL: json_response(GH_FULL, payload)})).fetch_jobs("acme")
    assert jobs == [
        JobListing(
            external_id="4461450008",
            title="Backend Engineer",
            url="https://job-boards.greenhouse.io/acme/jobs/1",
            text="About\n\nAPIs & data.",
        )
    ]


def test_greenhouse_probe_uses_the_light_endpoint() -> None:
    http = fake_http({GH_JOBS: json_response(GH_JOBS, {"jobs": []})})
    assert GreenhouseSource(http).probe("acme") is True
    assert requested_urls(http) == [GH_JOBS]


def test_greenhouse_unknown_board_is_none_and_errors_raise() -> None:
    assert GreenhouseSource(fake_http({})).fetch_jobs("acme") is None
    assert GreenhouseSource(fake_http({})).probe("acme") is False
    with pytest.raises(BoardUnavailableError, match="HTTP 503"):
        GreenhouseSource(fake_http({GH_FULL: failure(GH_FULL, 503)})).fetch_jobs("acme")
    with pytest.raises(BoardUnavailableError, match="offline"):
        GreenhouseSource(fake_http({GH_FULL: failure(GH_FULL)})).fetch_jobs("acme")
    with pytest.raises(BoardUnavailableError, match="not JSON"):
        GreenhouseSource(fake_http({GH_FULL: HttpResponse(GH_FULL, 200, "<html>")})).fetch_jobs("acme")


def test_greenhouse_200_without_jobs_array_is_not_a_board() -> None:
    assert GreenhouseSource(fake_http({GH_JOBS: json_response(GH_JOBS, {"error": "x"})})).probe("acme") is False


# --- Lever ------------------------------------------------------------------------------------------------


def test_lever_list_with_sections() -> None:
    payload = [
        {
            "id": "6ed76ce8-4156-4b60-b120-403538bd66cd",
            "text": "Platform Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/6ed76ce8",
            "descriptionPlain": "We run the platform.",
            "lists": [{"text": "Requirements", "content": "<li>Python</li><li>Kubernetes</li>"}],
            "additionalPlain": "Remote friendly.",
        }
    ]
    jobs = LeverSource(fake_http({LEVER: json_response(LEVER, payload)})).fetch_jobs("acme")
    assert jobs is not None
    assert (jobs[0].external_id, jobs[0].title, jobs[0].url) == ("6ed76ce8-4156-4b60-b120-403538bd66cd", "Platform Engineer", "https://jobs.lever.co/acme/6ed76ce8")
    assert jobs[0].text == "We run the platform.\n\nRequirements\n\n- Python\n- Kubernetes\n\nRemote friendly."


def test_lever_probe_asks_for_one_posting() -> None:
    probe_url = f"{LEVER}&limit=1"
    http = fake_http({probe_url: json_response(probe_url, [])})
    assert LeverSource(http).probe("acme") is True
    assert requested_urls(http) == [probe_url]


def test_lever_unknown_board() -> None:
    not_found = json_response(LEVER, {"ok": False, "error": "Document not found"}, status=404)
    assert LeverSource(fake_http({LEVER: not_found})).fetch_jobs("acme") is None


# --- Ashby ------------------------------------------------------------------------------------------------


def test_ashby_skips_unlisted_and_falls_back_to_html() -> None:
    payload = {
        "apiVersion": "1",
        "jobs": [
            {"id": "a1", "title": "Backend Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/a1", "descriptionPlain": "Plain.", "isListed": True},
            {"id": "a2", "title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/acme/a2", "isListed": False},
            {"id": "a3", "title": "Data Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/a3", "descriptionHtml": "<p>From HTML</p>"},
        ],
    }
    jobs = AshbySource(fake_http({ASHBY: json_response(ASHBY, payload)})).fetch_jobs("acme")
    assert jobs is not None
    assert [(job.external_id, job.text) for job in jobs] == [("a1", "Plain."), ("a3", "From HTML")]


def test_ashby_unknown_board_is_plain_text_404() -> None:
    assert AshbySource(fake_http({ASHBY: HttpResponse(ASHBY, 404, "Not Found")})).probe("acme") is False


# --- Comeet -----------------------------------------------------------------------------------------------


def _comeet_page(positions_json: str) -> str:
    """Laid out like the live page: the variable is declared first, unrelated arrays follow, then the assignment."""
    return (
        "<html><script>\n"
        "       var COMPANY_POSITIONS_DATA ;\n"
        "       var POSITION_DATA ;\n"
        '       var LOCALES = ["en", "he"];\n'
        '       COMPANY_DATA = {"name": "Acme"};\n'
        f"        COMPANY_POSITIONS_DATA = {positions_json};\n"
        "        POSITION_DATA = null;</script></html>"
    )


def test_comeet_positions_from_hosted_page() -> None:
    positions = (
        '[{"uid": "AC.F50", "name": "Backend Engineer", "is_internal": false,'
        ' "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/98.008/backend-engineer/AC.F50",'
        ' "custom_fields": {"details": [{"name": "Description", "value": "<p>Build APIs; ship [fast].</p>"},'
        ' {"name": "Requirements", "value": "<ul><li>Python</li></ul>"}]}},'
        ' {"uid": "AC.F51", "name": "Internal role", "is_internal": true}]'
    )
    jobs = ComeetSource(fake_http({COMEET: page(COMEET, _comeet_page(positions))})).fetch_jobs("acme/98.008")
    assert jobs == [
        JobListing(
            external_id="acme/98.008:AC.F50",
            title="Backend Engineer",
            url="https://www.comeet.com/jobs/acme/98.008/backend-engineer/AC.F50",
            text="Description\n\nBuild APIs; ship [fast].\n\nRequirements\n\n- Python",
        )
    ]


def test_comeet_declaration_without_assignment_is_not_a_board() -> None:
    declared_only = '<script>var COMPANY_POSITIONS_DATA ;\nvar LOCALES = ["en"];</script>'
    assert ComeetSource(fake_http({COMEET: page(COMEET, declared_only)})).fetch_jobs("acme/98.008") is None


def test_comeet_subdomain_slug_and_page_without_positions() -> None:
    subdomain = "https://acme.comeet.co/"
    http = fake_http({subdomain: page(subdomain, "<html>Welcome</html>")})
    assert ComeetSource(http).fetch_jobs("acme") is None
    assert requested_urls(http) == [subdomain]


def test_comeet_malformed_positions_raise() -> None:
    http = fake_http({COMEET: page(COMEET, _comeet_page("[{broken"))})
    with pytest.raises(BoardUnavailableError, match="not valid JSON"):
        ComeetSource(http).fetch_jobs("acme/98.008")
