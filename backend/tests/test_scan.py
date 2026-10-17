"""Scan: role filter on titles, dedup on (source, external_id), per-company errors, Workday and Comeet API boards,
scoring, and the profile's location rule before it."""

import json
from collections.abc import Mapping
from unittest.mock import MagicMock

import httpx
import pytest

from job_board.app_config import AppConfig
from job_board.boards.board_ref import BoardRef
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.enums.outcome import Outcome
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.fit_result import FitResult
from job_board.llm_settings import LlmSettings
from job_board.models.company import Company
from job_board.models.posting_patch import PostingPatch
from job_board.models.profile_patch import ProfilePatch
from job_board.models.run_summary import RunSummary
from job_board.posting_repository import PostingRepository
from job_board.profile_repository import ProfileRepository
from job_board.scan import Scan
from job_board.scorer import Scorer

from job_board.utils.json_values import as_str, dicts

from tests.http_fakes import FakeWeb, fixture_dict, fixture_list

ACME_JOBS = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
GLOBEX_JOBS = "https://api.lever.co/v0/postings/globex?mode=json"
WORKDAY_ROOT = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
COMEET_API = "https://www.comeet.co/careers-api/2.0/company/E6.001/positions?token=TESTTOKEN&details=true"


def _gh_job(job_id: int, title: str, location: str = "Tel Aviv, Israel") -> dict[str, object]:
    url = f"https://job-boards.greenhouse.io/acme/jobs/{job_id}"
    return {"id": job_id, "title": title, "absolute_url": url, "content": "", "location": {"name": location}}


ACME_BOARD = {
    "jobs": [
        _gh_job(1, "Senior AI Engineer"),
        _gh_job(2, "Security Researcher"),
        _gh_job(3, "AI Research Intern"),  # excluded role
        _gh_job(4, "Backend Engineer"),  # not a wanted role
        _gh_job(5, "Principal AI Product Manager"),  # excluded role
    ]
}


def _add(database: Database, name: str, board: BoardRef | None, verified: bool = True) -> None:
    finding = DiscoveryFinding(board=board, verified=verified, careers_url=None)
    CompanyRepository(database).record_discovery(CompanySeed(name, f"{name.lower()}.com"), finding)


def _live_in(database: Database, location: str) -> None:
    """Set the profile's location, which the scan's location rule reads."""
    ProfileRepository(database).update(ProfilePatch(location=location))


async def _scan(database: Database, web: FakeWeb, locations: tuple[str, ...] = ()) -> RunSummary:
    _live_in(database, "Israel")
    config = AppConfig(
        db_path=database.path,
        include_keywords=("AI + engineer", "researcher", "software engineer"),
        exclude_keywords=("intern", "product manager"),
        companies=(),
        locations=locations,
    )
    async with web.client() as http:
        return await Scan(config, database=database, http=http).run()


def _acme_web(board: Mapping[str, object] | None = None) -> FakeWeb:
    web = FakeWeb()
    web.json(ACME_JOBS, ACME_BOARD if board is None else board)
    return web


def _titles(database: Database) -> list[str]:
    return sorted(posting.title for posting in PostingRepository(database).list_all())


def _company(database: Database, name: str) -> Company:
    return next(company for company in CompanyRepository(database).list_all() if company.name == name)


@pytest.mark.anyio
async def test_only_wanted_roles_become_cards(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    summary = await _scan(database, _acme_web())
    assert (summary.ok, summary.failed) == (1, 0)
    assert _titles(database) == ["Security Researcher", "Senior AI Engineer"]
    posting = next(p for p in PostingRepository(database).list_all() if p.external_id == "1")
    assert (posting.source, posting.company, posting.status) == (Source.GREENHOUSE, "Acme", Status.NEW)


# --- dedup rule: UNIQUE(source, external_id); a rescan never duplicates, overwrites or resets a card ------


@pytest.mark.anyio
async def test_rescan_adds_nothing_and_keeps_status_outcome_and_note(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    await _scan(database, _acme_web())
    postings = PostingRepository(database)
    closed = next(p for p in postings.list_all() if p.external_id == "1")
    postings.save(PostingPatch(status=Status.CLOSED, outcome=Outcome.REJECTED, note="no reply").apply_to(closed))
    renamed = {"jobs": [_gh_job(1, "Senior AI Engineer (renamed)"), *ACME_BOARD["jobs"][1:]]}
    await _scan(database, _acme_web(renamed))
    assert len(postings.list_all()) == 2
    kept = postings.get(closed.id)
    assert kept is not None
    assert (kept.title, kept.status, kept.outcome, kept.note) == ("Senior AI Engineer", Status.CLOSED, Outcome.REJECTED, "no reply")


@pytest.mark.anyio
async def test_same_external_id_on_another_platform_is_a_different_posting(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add(database, "Globex", BoardRef(Platform.LEVER, "globex"))
    web = _acme_web()
    globex_job = {"id": "1", "text": "Staff AI Engineer", "hostedUrl": "https://jobs.lever.co/globex/1", "categories": {"location": "Haifa"}}
    web.json(GLOBEX_JOBS, [globex_job])
    await _scan(database, web)
    sources = sorted(posting.source for posting in PostingRepository(database).list_all() if posting.external_id == "1")
    assert sources == [Source.GREENHOUSE, Source.LEVER]


# --- which companies are scanned, errors ------------------------------------------------------------------


@pytest.mark.anyio
async def test_only_verified_enabled_companies_with_a_board_are_scanned(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add(database, "Unverified", BoardRef(Platform.GREENHOUSE, "unverified"), verified=False)
    _add(database, "Proprietary", None, verified=False)
    _add(database, "Disabled", BoardRef(Platform.GREENHOUSE, "disabled"))
    companies = CompanyRepository(database)
    companies.set_enabled(_company(database, "Disabled").id, False)
    web = _acme_web()
    summary = await _scan(database, web)
    assert summary.ok == 1
    assert web.urls() == [ACME_JOBS]


@pytest.mark.anyio
async def test_unreadable_boards_set_last_error_and_a_good_read_clears_it(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add(database, "Down", BoardRef(Platform.GREENHOUSE, "down"))
    _add(database, "Gone", BoardRef(Platform.LEVER, "gone"))
    web = _acme_web()
    web.status("https://boards-api.greenhouse.io/v1/boards/down/jobs?content=true", 503)
    summary = await _scan(database, web)
    assert (summary.ok, summary.failed) == (1, 2)
    assert "HTTP 503" in (_company(database, "Down").last_error or "")
    assert "no longer exists" in (_company(database, "Gone").last_error or "")
    assert len(_titles(database)) == 2  # Acme was still scanned
    recovered = _acme_web()
    recovered.json("https://boards-api.greenhouse.io/v1/boards/down/jobs?content=true", {"jobs": []})
    await _scan(database, recovered)
    assert _company(database, "Down").last_error is None


@pytest.mark.anyio
async def test_no_companies_is_an_empty_summary(database: Database) -> None:
    summary = await _scan(database, FakeWeb())
    assert (summary.ok, summary.failed) == (0, 0)


# --- Workday and Comeet API -------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_workday_board_is_searched_per_role_and_filtered_to_israel(database: Database) -> None:
    board = BoardRef(Platform.WORKDAY, "nvidia/NVIDIAExternalCareerSite", tenant="nvidia", wd_host="wd5", site="NVIDIAExternalCareerSite")
    _add(database, "Nvidia", board)
    listing = fixture_dict("workday_listing_israel.json")
    path = as_str(dicts(listing["jobPostings"])[0]["externalPath"])
    web = FakeWeb()

    def search(request: httpx.Request) -> httpx.Response:
        term = json.loads(request.content)["searchText"]
        answer: object = listing if term == "software engineer" else {"total": 0, "jobPostings": []}
        return httpx.Response(200, json=answer, request=request)

    web.route("POST", f"{WORKDAY_ROOT}/jobs", search)
    web.fixture(f"{WORKDAY_ROOT}{path}", "workday_job_israel.json")
    summary = await _scan(database, web, locations=("Israel",))
    assert summary.ok == 1
    stored = PostingRepository(database).list_all()
    assert [(p.source, p.title, p.status) for p in stored] == [(Source.WORKDAY, "Senior System Software Engineer - Signing Platform", Status.NEW)]
    assert stored[0].country == "IL"  # from the detail's jobRequisitionLocation.country.alpha2Code
    searched = sorted(json.loads(request.content)["searchText"] for request in web.requests if request.method == "POST")
    assert searched == ["AI engineer", "researcher", "software engineer"]


@pytest.mark.anyio
async def test_comeet_api_board(database: Database) -> None:
    _add(database, "AI21 Labs", BoardRef(Platform.COMEET, "AI21/E6.001", company_uid="E6.001", token="TESTTOKEN"))
    recorded = fixture_list("comeet_positions.json")
    web = FakeWeb()
    applied_ai: dict[str, object] = {"uid": "ZZ.001", "name": "Software Engineer, Applied AI", "details": []}
    web.json(COMEET_API, [*recorded, applied_ai])
    recorded_position = {**dicts(recorded)[0], "uid": "ZZ.002", "name": "Software Engineer, Platform"}
    web.json(COMEET_API, [*recorded, applied_ai, recorded_position])
    await _scan(database, web)
    stored = PostingRepository(database).list_all()
    # "Deep Learning Engineer" is not a wanted role here; ZZ.001 has no location and nothing in it names Israel.
    assert [p.external_id for p in stored] == ["ZZ.002"]
    assert (stored[0].location, stored[0].country, stored[0].status) == ("Tel Aviv, Israel", "IL", Status.NEW)


# --- scoring ----------------------------------------------------------------------------------------------


def _scorer_by_title(fits: dict[str, FitResult]) -> MagicMock:
    scorer = MagicMock(spec=Scorer)

    async def score(*, title: str, company: str, location: str, text: str) -> FitResult:
        del company, location, text
        return fits[title]

    scorer.score.side_effect = score
    return scorer


async def _scan_scored(database: Database, web: FakeWeb, scorer: MagicMock, location: str = "Israel") -> RunSummary:
    _live_in(database, location)
    config = AppConfig(
        db_path=database.path,
        include_keywords=("AI + engineer", "researcher"),
        exclude_keywords=("intern", "product manager"),
        companies=(),
        llm=LlmSettings(threshold=6),
    )
    async with web.client() as http:
        return await Scan(config, database=database, http=http, scorer=scorer).run()


@pytest.mark.anyio
async def test_new_jobs_are_scored_and_low_fits_go_to_the_archive(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    scorer = _scorer_by_title(
        {"Senior AI Engineer": FitResult(8, "strong", ("Go",)), "Security Researcher": FitResult(3, "different field")}
    )
    await _scan_scored(database, _acme_web(), scorer)
    by_title = {posting.title: posting for posting in PostingRepository(database).list_all()}
    engineer, researcher = by_title["Senior AI Engineer"], by_title["Security Researcher"]
    assert (engineer.status, engineer.fit, engineer.fit_reason, engineer.fit_gaps) == (Status.NEW, 8, "strong", ["Go"])
    assert (researcher.status, researcher.outcome, researcher.fit) == (Status.CLOSED, Outcome.NOT_RELEVANT, 3)
    assert scorer.score.await_count == 2  # only titles that passed the role filter


@pytest.mark.anyio
async def test_unscorable_jobs_stay_new(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    unscorable = FitResult(None, "parse error")
    await _scan_scored(database, _acme_web(), _scorer_by_title({"Senior AI Engineer": unscorable, "Security Researcher": unscorable}))
    assert {(p.status, p.fit, p.fit_reason) for p in PostingRepository(database).list_all()} == {(Status.NEW, None, "parse error")}


@pytest.mark.anyio
async def test_jobs_already_stored_are_not_scored_again(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    fits = {"Senior AI Engineer": FitResult(8, "strong"), "Security Researcher": FitResult(7, "ok")}
    await _scan_scored(database, _acme_web(), _scorer_by_title(fits))
    second = _scorer_by_title(fits)
    await _scan_scored(database, _acme_web(), second)
    second.score.assert_not_awaited()


@pytest.mark.anyio
async def test_location_is_stored_with_the_job(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    board = {"jobs": [_gh_job(1, "Senior AI Engineer (Remote)", location="Tel Aviv-Yafo, Israel")]}
    await _scan_scored(database, _acme_web(board), _scorer_by_title({"Senior AI Engineer (Remote)": FitResult(7, "ok")}))
    stored = PostingRepository(database).list_all()[0]
    assert (stored.location, stored.country, stored.is_remote) == ("Tel Aviv-Yafo, Israel", "IL", True)


# --- the location rule ------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_jobs_outside_the_profile_location_are_not_stored_or_scored(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    board = {"jobs": [_gh_job(1, "Senior AI Engineer", location="Herzliya"), _gh_job(2, "Security Researcher", location="Berlin, Germany")]}
    scorer = _scorer_by_title({"Senior AI Engineer": FitResult(8, "strong")})  # scoring the researcher would raise KeyError
    await _scan_scored(database, _acme_web(board), scorer)
    stored = PostingRepository(database).list_all()
    assert [(p.title, p.status, p.country) for p in stored] == [("Senior AI Engineer", Status.NEW, "IL")]
    assert scorer.score.await_count == 1
    later = _scorer_by_title({"Security Researcher": FitResult(7, "ok")})
    await _scan_scored(database, _acme_web(board), later, location="Germany")  # a later scan looks at it again
    assert sorted(p.title for p in PostingRepository(database).list_all()) == ["Security Researcher", "Senior AI Engineer"]


@pytest.mark.anyio
async def test_without_a_profile_location_nothing_is_stored(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    scorer = _scorer_by_title({})
    await _scan_scored(database, _acme_web(), scorer, location="")
    assert PostingRepository(database).list_all() == []
    scorer.score.assert_not_awaited()


@pytest.mark.anyio
async def test_a_rescan_fills_in_the_location_of_jobs_stored_without_one(database: Database) -> None:
    _add(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    postings = PostingRepository(database)
    old, _ = postings.insert(source=Source.GREENHOUSE, external_id="1", company="Acme", title="Senior AI Engineer", url="x", text="")
    await _scan_scored(database, _acme_web(), _scorer_by_title({"Security Researcher": FitResult(7, "ok")}))
    filled = postings.get(old.id)
    assert filled is not None and (filled.location, filled.country, filled.status) == ("Tel Aviv, Israel", "IL", Status.NEW)
