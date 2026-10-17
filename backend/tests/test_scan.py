"""Scan: role filter on titles, dedup on (source, external_id), per-company errors, Workday and Comeet API boards."""

import json
from collections.abc import Mapping

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
from job_board.models.company import Company
from job_board.models.posting_patch import PostingPatch
from job_board.models.run_summary import RunSummary
from job_board.posting_repository import PostingRepository
from job_board.scan import Scan

from job_board.utils.json_values import as_str, dicts

from tests.http_fakes import FakeWeb, fixture_dict, fixture_list

ACME_JOBS = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
GLOBEX_JOBS = "https://api.lever.co/v0/postings/globex?mode=json"
WORKDAY_ROOT = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
COMEET_API = "https://www.comeet.co/careers-api/2.0/company/E6.001/positions?token=TESTTOKEN&details=true"


def _gh_job(job_id: int, title: str) -> dict[str, object]:
    return {"id": job_id, "title": title, "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{job_id}", "content": ""}


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


async def _scan(database: Database, web: FakeWeb, locations: tuple[str, ...] = ()) -> RunSummary:
    config = AppConfig(
        db_path=database.path,
        include_keywords=("AI + engineer", "researcher", "software engineer"),
        exclude_keywords=("intern", "product manager"),
        companies=(),
        workday_locations=locations,
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
    web.json(GLOBEX_JOBS, [{"id": "1", "text": "Staff AI Engineer", "hostedUrl": "https://jobs.lever.co/globex/1"}])
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
    assert [(p.source, p.title) for p in stored] == [(Source.WORKDAY, "Senior System Software Engineer - Signing Platform")]
    searched = sorted(json.loads(request.content)["searchText"] for request in web.requests if request.method == "POST")
    assert searched == ["AI engineer", "researcher", "software engineer"]


@pytest.mark.anyio
async def test_comeet_api_board(database: Database) -> None:
    _add(database, "AI21 Labs", BoardRef(Platform.COMEET, "AI21/E6.001", company_uid="E6.001", token="TESTTOKEN"))
    recorded = fixture_list("comeet_positions.json")
    web = FakeWeb()
    applied_ai: dict[str, object] = {"uid": "ZZ.001", "name": "Software Engineer, Applied AI", "details": []}
    web.json(COMEET_API, [*recorded, applied_ai])
    await _scan(database, web)
    assert [p.external_id for p in PostingRepository(database).list_all()] == ["ZZ.001"]  # "Deep Learning Engineer" is not a wanted role here
