"""Board sources against recorded API answers (tests/fixtures, trimmed real responses from 2026-10-17)."""

import json

import httpx
import pytest

from job_board.boards.ashby_source import AshbySource
from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.comeet_source import ComeetSource
from job_board.boards.greenhouse_source import GreenhouseSource
from job_board.boards.lever_source import LeverSource
from job_board.boards.workday_source import WorkdaySource
from job_board.enums.platform import Platform
from job_board.keyword_filter import KeywordFilter

from job_board.utils.json_values import as_str, dicts

from tests.http_fakes import FakeWeb, fixture_json, fixture_dict, fixture_list

GH_JOBS = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs"
LEVER = "https://api.lever.co/v0/postings/palantir?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/openai"
COMEET_API = "https://www.comeet.co/careers-api/2.0/company/E6.001/positions?token=TESTTOKEN&details=true"
COMEET_PAGE = "https://www.comeet.com/jobs/tripleten/98.008"
WORKDAY_ROOT = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
WORKDAY = BoardRef(Platform.WORKDAY, "nvidia/NVIDIAExternalCareerSite", tenant="nvidia", wd_host="wd5", site="NVIDIAExternalCareerSite")


def _board(platform: Platform, slug: str) -> BoardRef:
    return BoardRef(platform, slug)


# --- Greenhouse -------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_greenhouse_jobs_from_recorded_board() -> None:
    web = FakeWeb()
    web.fixture(f"{GH_JOBS}?content=true", "greenhouse_jobs.json")
    async with web.client() as http:
        jobs = await GreenhouseSource(http).fetch_jobs(_board(Platform.GREENHOUSE, "anthropic"))
    assert jobs is not None and len(jobs) == 2
    assert jobs[0].external_id == "4461450008"
    assert jobs[0].url.startswith("https://job-boards.greenhouse.io/anthropic/jobs/")
    assert jobs[0].text.startswith("About Anthropic")  # entity-encoded HTML decoded to text
    assert "&lt;" not in jobs[0].text and "<" not in jobs[0].text


@pytest.mark.anyio
async def test_greenhouse_probe_and_board_name() -> None:
    web = FakeWeb()
    web.json(GH_JOBS, {"jobs": []})
    web.fixture("https://boards-api.greenhouse.io/v1/boards/anthropic", "greenhouse_board.json")
    async with web.client() as http:
        source = GreenhouseSource(http)
        assert await source.probe(_board(Platform.GREENHOUSE, "anthropic")) is True
        assert await source.board_name(_board(Platform.GREENHOUSE, "anthropic")) == "Anthropic"
    assert web.urls()[0] == GH_JOBS  # the light endpoint, without content=true


@pytest.mark.anyio
async def test_greenhouse_unknown_board_is_none_and_errors_raise() -> None:
    web = FakeWeb()
    web.status(f"{GH_JOBS}?content=true", 503)
    async with web.client() as http:
        source = GreenhouseSource(http)
        assert await source.fetch_jobs(_board(Platform.GREENHOUSE, "nope")) is None
        assert await source.probe(_board(Platform.GREENHOUSE, "nope")) is False
        with pytest.raises(BoardUnavailableError, match="HTTP 503"):
            await source.fetch_jobs(_board(Platform.GREENHOUSE, "anthropic"))


# --- Lever ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lever_postings_from_recorded_board() -> None:
    web = FakeWeb()
    web.fixture(LEVER, "lever_postings.json")
    async with web.client() as http:
        jobs = await LeverSource(http).fetch_jobs(_board(Platform.LEVER, "palantir"))
    recorded = fixture_list("lever_postings.json")
    assert jobs is not None and len(jobs) == len(recorded)
    assert jobs[0].url.startswith("https://jobs.lever.co/palantir/")
    assert jobs[0].text  # descriptionPlain + list sections + additionalPlain


@pytest.mark.anyio
async def test_lever_probe_asks_for_one_posting() -> None:
    web = FakeWeb()
    web.json(f"{LEVER}&limit=1", [])
    async with web.client() as http:
        assert await LeverSource(http).probe(_board(Platform.LEVER, "palantir")) is True
    assert web.urls() == [f"{LEVER}&limit=1"]


# --- Ashby ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ashby_jobs_from_recorded_board_skip_unlisted() -> None:
    recorded = fixture_dict("ashby_jobs.json")
    jobs_payload = dicts(recorded["jobs"])
    hidden: dict[str, object] = {"id": "hidden", "title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/openai/hidden", "isListed": False}
    web = FakeWeb()
    web.json(ASHBY, {**recorded, "jobs": [*jobs_payload, hidden]})
    async with web.client() as http:
        jobs = await AshbySource(http).fetch_jobs(_board(Platform.ASHBY, "openai"))
    assert jobs is not None and [job.external_id for job in jobs] == [job["id"] for job in jobs_payload]


# --- Comeet -----------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_comeet_api_positions_with_token() -> None:
    web = FakeWeb()
    web.fixture(COMEET_API, "comeet_positions.json")
    board = BoardRef(Platform.COMEET, "AI21/E6.001", company_uid="E6.001", token="TESTTOKEN")
    async with web.client() as http:
        jobs = await ComeetSource(http).fetch_jobs(board)
    assert jobs is not None and len(jobs) >= 1
    first = jobs[0]
    assert (first.external_id, first.title) == ("CC.372", "Deep Learning Engineer")  # external_id = position uid
    assert first.url == "https://www.comeet.com/jobs/ai21/E6.001/deep-learning-engineer/CC.372"
    assert first.text.startswith("Description\n\nOur team is looking for a Deep Learning Engineer.")


def _hosted_page(positions: object) -> str:
    """Laid out like the live page: the variable is declared first, unrelated arrays follow, then the assignment."""
    return (
        "<html><script>\n"
        "       var COMPANY_POSITIONS_DATA ;\n"
        '       var LOCALES = ["en", "he"];\n'
        f"       COMPANY_POSITIONS_DATA = {json.dumps(positions)};\n"
        "       POSITION_DATA = null;</script></html>"
    )


@pytest.mark.anyio
async def test_comeet_hosted_page_without_token() -> None:
    recorded = fixture_list("comeet_positions.json")
    internal: dict[str, object] = {"uid": "XX.001", "name": "Internal only", "is_internal": True}
    web = FakeWeb()
    web.page(COMEET_PAGE, _hosted_page([*recorded, internal]))
    async with web.client() as http:
        jobs = await ComeetSource(http).fetch_jobs(BoardRef(Platform.COMEET, "tripleten/98.008", company_uid="98.008"))
    assert jobs is not None and "XX.001" not in [job.external_id for job in jobs] and jobs[0].external_id == "CC.372"


@pytest.mark.anyio
async def test_comeet_page_without_positions_is_not_a_board() -> None:
    web = FakeWeb()
    web.page("https://acme.comeet.co/", "<script>var COMPANY_POSITIONS_DATA ;</script>")
    async with web.client() as http:
        assert await ComeetSource(http).fetch_jobs(BoardRef(Platform.COMEET, "acme")) is None


# --- Workday ----------------------------------------------------------------------------------------------


def _workday_search(answers: dict[str, object]) -> FakeWeb:
    """A Workday site whose jobs endpoint answers by searchText (unknown terms find nothing)."""
    web = FakeWeb()

    def search(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json=answers.get(body["searchText"], {"total": 0, "jobPostings": []}), request=request)

    web.route("POST", f"{WORKDAY_ROOT}/jobs", search)
    return web


@pytest.mark.anyio
async def test_workday_searches_each_keyword_and_keeps_israel_jobs() -> None:
    listing = fixture_dict("workday_listing_israel.json")
    path = as_str(dicts(listing["jobPostings"])[0]["externalPath"])
    web = _workday_search({"machine learning engineer": fixture_json("workday_jobs.json"), "software engineer": listing})
    web.fixture(f"{WORKDAY_ROOT}{path}", "workday_job_israel.json")
    roles = KeywordFilter(["machine learning + engineer", "software engineer"], [])
    async with web.client() as http:
        jobs = await WorkdaySource(http, roles, ["Israel"]).fetch_jobs(WORKDAY)
    searched = [json.loads(request.content)["searchText"] for request in web.requests if request.method == "POST"]
    assert sorted(searched) == ["machine learning engineer", "software engineer"]  # one search per role
    assert jobs is not None and len(jobs) == 1  # the "3 Locations" job is in Israel; others are elsewhere
    job = jobs[0]
    assert job.external_id == "Senior-System-Software-Engineer---Signing-Platform_JR2025357-1"  # jobPostingId
    assert job.url.startswith("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/")
    assert job.text


@pytest.mark.anyio
async def test_workday_details_are_only_fetched_for_possible_location_matches() -> None:
    web = _workday_search({"machine learning engineer": fixture_json("workday_jobs.json")})
    async with web.client() as http:
        jobs = await WorkdaySource(http, KeywordFilter(["machine learning + engineer"], []), ["Israel"]).fetch_jobs(WORKDAY)
    details = web.urls("GET")
    assert jobs == []
    assert len(details) == 1  # only the "2 Locations" job needed its detail; Shanghai and Santa Clara did not


@pytest.mark.anyio
async def test_workday_pages_through_results() -> None:
    page = {"jobPostings": [{"title": "Job", "externalPath": f"/job/x_{index}", "locationsText": "US"} for index in range(20)]}
    offsets: list[int] = []

    def search(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        offsets.append(offset)
        return httpx.Response(200, json={**page, "total": 45}, request=request)

    web = FakeWeb()
    web.route("POST", f"{WORKDAY_ROOT}/jobs", search)
    async with web.client() as http:
        await WorkdaySource(http, KeywordFilter(["llm"], []), ["Israel"]).fetch_jobs(WORKDAY)
    assert offsets == [0, 20, 40]
    assert web.urls("GET") == []  # no title matched the role, so no detail was fetched


@pytest.mark.anyio
async def test_workday_unknown_site_is_none_and_probe_false() -> None:
    web = FakeWeb()
    async with web.client() as http:
        source = WorkdaySource(http, KeywordFilter(["llm"], []))
        assert await source.fetch_jobs(WORKDAY) is None
        assert await source.probe(WORKDAY) is False


@pytest.mark.anyio
async def test_sources_report_the_job_location() -> None:
    web = FakeWeb()
    web.fixture(f"{GH_JOBS}?content=true", "greenhouse_jobs.json")
    web.fixture(LEVER, "lever_postings.json")
    web.fixture(ASHBY, "ashby_jobs.json")
    web.fixture(COMEET_API, "comeet_positions.json")
    async with web.client() as http:
        greenhouse = await GreenhouseSource(http).fetch_jobs(_board(Platform.GREENHOUSE, "anthropic"))
        lever = await LeverSource(http).fetch_jobs(_board(Platform.LEVER, "palantir"))
        ashby = await AshbySource(http).fetch_jobs(_board(Platform.ASHBY, "openai"))
        comeet = await ComeetSource(http).fetch_jobs(BoardRef(Platform.COMEET, "AI21/E6.001", company_uid="E6.001", token="TESTTOKEN"))
    assert greenhouse and lever and ashby and comeet
    assert all(job.location for job in (greenhouse[0], lever[0], ashby[0], comeet[0]))
    assert comeet[0].location.startswith("Tel Aviv, Israel")
