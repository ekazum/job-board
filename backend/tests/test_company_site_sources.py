"""Single-company careers sites (Google, Microsoft, Apple, Amazon, Meta) against recorded answers from 2026-10-17."""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from job_board.boards.amazon_source import SEARCH_URL as AMAZON_SEARCH
from job_board.boards.amazon_source import AmazonSource
from job_board.boards.apple_source import API_ROOT as APPLE_API
from job_board.boards.apple_source import AppleSource
from job_board.boards.board_ref import BoardRef
from job_board.boards.board_unavailable_error import BoardUnavailableError
from job_board.boards.google_source import SEARCH_URL as GOOGLE_SEARCH
from job_board.boards.google_source import GoogleSource
from job_board.boards.meta_source import GRAPHQL_URL, OFFICES_QUERY, SEARCH_PAGE, SEARCH_QUERY, MetaSource
from job_board.boards.microsoft_source import API_ROOT as MICROSOFT_API
from job_board.boards.microsoft_source import MicrosoftSource
from job_board.enums.platform import Platform
from job_board.keyword_filter import KeywordFilter
from job_board.utils.json_values import as_dict

from tests.http_fakes import FakeWeb, fixture_dict, fixture_json, fixture_text

GOOGLE = BoardRef(Platform.GOOGLE, "google")
MICROSOFT = BoardRef(Platform.MICROSOFT, "microsoft")
APPLE = BoardRef(Platform.APPLE, "apple")
AMAZON = BoardRef(Platform.AMAZON, "amazon")
META = BoardRef(Platform.META, "meta")


def _form(request: httpx.Request) -> dict[str, str]:
    """The url-encoded form fields of a request."""
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


# --- Google -----------------------------------------------------------------------------------------------


def _google_args(request: httpx.Request) -> list[object]:
    """The search arguments inside f.req: [query, ..., [[location]], page]."""
    rpc = json.loads(_form(request)["f.req"])[0][0]
    args: list[object] = json.loads(rpc[1])[0]
    return args


def _google_answer(jobs: list[object], total: int) -> str:
    """A batchexecute answer carrying these jobs."""
    envelope = ["wrb.fr", "r06xKb", json.dumps([jobs, None, total, 20]), None, None, None, "generic"]
    return ")]}'\n\n" + json.dumps([envelope, ["di", 100]])


def _google_jobs() -> list[object]:
    """The jobs of the recorded answer."""
    envelopes = json.loads(fixture_text("google_search.txt").removeprefix(")]}'"))
    jobs: list[object] = json.loads(envelopes[0][2])[0]
    return jobs


@pytest.mark.anyio
async def test_google_searches_each_role_in_the_locations_and_keeps_wanted_titles() -> None:
    searched: list[list[object]] = []

    def search(request: httpx.Request) -> httpx.Response:
        searched.append(_google_args(request))
        return httpx.Response(200, text=fixture_text("google_search.txt"), request=request)

    web = FakeWeb()
    web.route("POST", GOOGLE_SEARCH, search)
    roles = KeywordFilter(["engineer", "data scientist"], ["intern"])
    async with web.client() as http:
        jobs = await GoogleSource(http, roles, ["Israel"]).fetch_jobs(GOOGLE)
    assert sorted((args[0], args[6], args[7]) for args in searched) == [("data scientist", [["Israel"]], 1), ("engineer", [["Israel"]], 1)]
    assert jobs is not None
    assert sorted(job.title for job in jobs) == ["Research Data Scientist II, Waze", "Senior Front-End CAD Engineer, CPU, Google Cloud"]
    cad = next(job for job in jobs if "CAD" in job.title)  # found by both searches, kept once
    assert cad.url == f"https://www.google.com/about/careers/applications/jobs/results/{cad.external_id}"
    assert cad.location == "Haifa, Israel | Tel Aviv, Israel"
    assert "Minimum qualifications:" in cad.text and "<" not in cad.text


@pytest.mark.anyio
async def test_google_keeps_only_configured_locations_and_pages_through_results() -> None:
    jobs = _google_jobs()
    pages: list[object] = []

    def search(request: httpx.Request) -> httpx.Response:
        page = _google_args(request)[7]
        pages.append(page)
        return httpx.Response(200, text=_google_answer(jobs[:2] if page == 1 else jobs[2:], 3), request=request)

    web = FakeWeb()
    web.route("POST", GOOGLE_SEARCH, search)
    async with web.client() as http:
        found = await GoogleSource(http, KeywordFilter(["engineer", "scientist"], []), ["Haifa"]).fetch_jobs(GOOGLE)
    assert sorted(pages, key=str) == [1, 1, 2, 2]  # two terms, two pages each
    assert found is not None and [job.title for job in found] == ["Senior Front-End CAD Engineer, CPU, Google Cloud"]


@pytest.mark.anyio
async def test_google_missing_search_is_none_and_a_bad_answer_raises() -> None:
    web = FakeWeb()
    async with web.client() as http:
        assert await GoogleSource(http).fetch_jobs(GOOGLE) is None
        assert await GoogleSource(http).probe(GOOGLE) is False
    web.route("POST", GOOGLE_SEARCH, lambda request: httpx.Response(200, text=')]}\'\n\n[["di", 1]]', request=request))
    async with web.client() as http:
        with pytest.raises(BoardUnavailableError, match="no r06xKb result"):
            await GoogleSource(http).fetch_jobs(GOOGLE)


# --- Microsoft --------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_microsoft_searches_each_role_and_reads_details_of_wanted_positions_only() -> None:
    searched: list[dict[str, str]] = []

    def search(request: httpx.Request) -> httpx.Response:
        searched.append(dict(request.url.params))
        return httpx.Response(200, json=fixture_json("microsoft_search.json"), request=request)

    web = FakeWeb()
    web.route_any_query("GET", f"{MICROSOFT_API}/search", search)
    details = f"{MICROSOFT_API}/position_details?position_id=1970393556959639&domain=microsoft.com&hl=en"
    web.fixture(details, "microsoft_position.json")
    async with web.client() as http:
        jobs = await MicrosoftSource(http, KeywordFilter(["researcher"], []), ["Israel"]).fetch_jobs(MICROSOFT)
    assert searched == [{"domain": "microsoft.com", "query": "researcher", "location": "Israel", "start": "0"}]
    detail_requests = [url for url in web.urls() if "position_details" in url]
    assert len(detail_requests) == 2  # both researchers; the engineer's details are never fetched
    assert jobs is not None and len(jobs) == 1  # the second researcher's details are missing (404), so it is skipped
    job = jobs[0]
    assert (job.external_id, job.url) == ("1970393556959639", "https://apply.careers.microsoft.com/careers/job/1970393556959639")
    assert job.location.startswith("Israel, Multiple Locations, Multiple Locations | Israel, Tel Aviv, Herzliya")
    assert job.text.startswith("Overview")


@pytest.mark.anyio
async def test_microsoft_pages_with_start() -> None:
    starts: list[str] = []
    position = {"id": 1, "name": "Chef", "locations": ["Israel, Haifa"]}

    def search(request: httpx.Request) -> httpx.Response:
        starts.append(request.url.params["start"])
        return httpx.Response(200, json={"data": {"positions": [position] * 10, "count": 25}}, request=request)

    web = FakeWeb()
    web.route_any_query("GET", f"{MICROSOFT_API}/search", search)
    async with web.client() as http:
        assert await MicrosoftSource(http, KeywordFilter(["researcher"], [])).fetch_jobs(MICROSOFT) == []
    assert starts == ["0", "10", "20"]


# --- Apple ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_apple_searches_its_location_ids_and_merges_a_position_across_cities() -> None:
    bodies: list[dict[str, object]] = []

    def search(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=fixture_json("apple_search.json"), request=request)

    web = FakeWeb()
    web.fixture(f"{APPLE_API}/refData/postlocation?input=Israel", "apple_locations.json")
    web.route("POST", f"{APPLE_API}/search", search)
    web.fixture(f"{APPLE_API}/jobDetails/200687183-1451?locale=en-us", "apple_job.json")
    async with web.client() as http:
        jobs = await AppleSource(http, KeywordFilter(["layout + engineer"], []), ["Israel"]).fetch_jobs(APPLE)
    assert [(body["query"], body["filters"], body["page"]) for body in bodies] == [("layout engineer", {"locations": ["postLocation-ISR"]}, 1)]
    assert jobs is not None and len(jobs) == 1  # one position open in Haifa and Herzliya
    job = jobs[0]
    assert (job.external_id, job.location) == ("200687183", "Haifa, Israel | Herzliya, Israel")
    assert job.url == "https://jobs.apple.com/en-us/details/200687183-1451/analog-layout-automation-engineer"
    assert "Minimum qualifications:\n" in job.text and "Preferred qualifications:\n" in job.text


@pytest.mark.anyio
async def test_apple_unknown_location_searches_nothing() -> None:
    web = FakeWeb()
    web.json(f"{APPLE_API}/refData/postlocation?input=Atlantis", {"res": []})
    async with web.client() as http:
        assert await AppleSource(http, KeywordFilter(["engineer"], []), ["Atlantis"]).fetch_jobs(APPLE) == []
    assert web.urls("POST") == []


# --- Amazon -----------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_amazon_looks_up_the_country_code_and_searches_each_role_in_it() -> None:
    searched: list[dict[str, str]] = []

    def search(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        lookup = params["base_query"] == "Israel"
        if not lookup:
            searched.append(params)
        return httpx.Response(200, json=fixture_json("amazon_lookup.json" if lookup else "amazon_search.json"), request=request)

    web = FakeWeb()
    web.route_any_query("GET", AMAZON_SEARCH, search)
    roles = KeywordFilter(["machine learning + engineer", "ML + engineer"], [])
    async with web.client() as http:
        jobs = await AmazonSource(http, roles, ["Israel"]).fetch_jobs(AMAZON)
    assert sorted((params["base_query"], params["country"]) for params in searched) == [("ML engineer", "ISR"), ("machine learning engineer", "ISR")]
    assert jobs is not None and len(jobs) == 2  # each found by both searches, kept once
    job = jobs[0]
    assert (job.location, job.url.startswith("https://www.amazon.jobs/en/jobs/")) == ("Israel, Tel Aviv", True)
    assert "Basic qualifications:" in job.text and "<br" not in job.text


@pytest.mark.anyio
async def test_amazon_location_without_a_country_searches_nothing() -> None:
    web = FakeWeb()
    web.route_any_query("GET", AMAZON_SEARCH, lambda request: httpx.Response(200, json=fixture_json("amazon_lookup.json"), request=request))
    async with web.client() as http:
        assert await AmazonSource(http, KeywordFilter(["engineer"], []), ["Atlantis"]).fetch_jobs(AMAZON) == []
    assert len(web.requests) == 1  # the lookup; the jobs it found are all in Israel


# --- Meta -------------------------------------------------------------------------------------------------


def _meta_web(answer: dict[str, object] | None = None) -> tuple[FakeWeb, list[dict[str, object]]]:
    """Meta's search page, GraphQL (offices, then search) and one job page; also returns the search inputs sent."""
    sent: list[dict[str, object]] = []

    def graphql(request: httpx.Request) -> httpx.Response:
        form = _form(request)
        assert (form["lsd"], request.headers["x-fb-lsd"]) == ("TESTLSD", "TESTLSD")
        if form["doc_id"] == OFFICES_QUERY:
            return httpx.Response(200, json=fixture_dict("meta_offices.json"), request=request)
        assert form["doc_id"] == SEARCH_QUERY
        sent.append(as_dict(json.loads(form["variables"]).get("search_input")) or {})
        return httpx.Response(200, json=answer or fixture_dict("meta_search.json"), request=request)

    web = FakeWeb()
    web.page(SEARCH_PAGE, fixture_text("meta_jobsearch.html"))
    web.route("POST", GRAPHQL_URL, graphql)
    web.page("https://www.metacareers.com/jobs/2082780019279407/", fixture_text("meta_job.html"))
    return web, sent


@pytest.mark.anyio
async def test_meta_searches_the_offices_of_the_locations_and_reads_the_job_page() -> None:
    web, sent = _meta_web()
    async with web.client() as http:
        jobs = await MetaSource(http, KeywordFilter(["software engineer"], []), ["Israel"]).fetch_jobs(META)
    assert [(search_input["q"], search_input["offices"]) for search_input in sent] == [
        ("software engineer", ["Tel Aviv, Israel"])  # London, UK is not in Israel
    ]
    assert jobs is not None and len(jobs) == 1  # the other software engineer's page is missing (404), so it is skipped
    job = jobs[0]
    assert (job.external_id, job.title, job.location) == ("2082780019279407", "Software Engineer, Systems", "Tel Aviv, Israel")
    assert job.url == "https://www.metacareers.com/jobs/2082780019279407/"
    assert job.text.startswith("Meta is seeking")


@pytest.mark.anyio
async def test_meta_graphql_errors_raise() -> None:
    web, _ = _meta_web({"errors": [{"message": "A server error missing_required_variable_value occured."}]})
    async with web.client() as http:
        with pytest.raises(BoardUnavailableError, match="missing_required_variable_value"):
            await MetaSource(http, KeywordFilter(["engineer"], []), ["Israel"]).fetch_jobs(META)
