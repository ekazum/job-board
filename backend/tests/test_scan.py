"""Scan: keyword filter on title + text, dedup on (source, external_id), skipped companies, issues."""

from collections.abc import Mapping

from job_board.app_config import AppConfig
from job_board.boards.board_ref import BoardRef
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.enums.platform import Platform
from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.http_response import HttpResponse
from job_board.models.posting_patch import PostingPatch
from job_board.models.scan_result import ScanResult
from job_board.posting_repository import PostingRepository
from job_board.scan import Scan

from tests.http_fakes import failure, fake_http, json_response

ACME_JOBS = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
GLOBEX_JOBS = "https://api.lever.co/v0/postings/globex?mode=json"


def _gh_job(job_id: int, title: str, content: str = "") -> dict[str, object]:
    return {"id": job_id, "title": title, "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{job_id}", "content": content}


ACME_BOARD = {
    "jobs": [
        _gh_job(1, "Backend Engineer"),
        _gh_job(2, "Software Engineer", "&lt;p&gt;Our stack: Python.&lt;/p&gt;"),  # include keyword only in text
        _gh_job(3, "Backend Intern"),  # exclude keyword in title
        _gh_job(4, "Backend Engineer, Payments", "&lt;p&gt;You will mentor an intern.&lt;/p&gt;"),  # exclude in text
        _gh_job(5, "Account Executive"),  # no include keyword
    ]
}
ACME_RESPONSES = {ACME_JOBS: json_response(ACME_JOBS, ACME_BOARD)}


def _add_company(database: Database, name: str, board: BoardRef | None, verified: bool = True) -> None:
    finding = DiscoveryFinding(board=board, verified=verified, careers_url=None)
    CompanyRepository(database).record_discovery(CompanySeed(name, f"{name.lower()}.com"), finding)


def _scan(database: Database, responses: Mapping[str, HttpResponse]) -> ScanResult:
    config = AppConfig(db_path=database.path, include_keywords=("backend", "python"), exclude_keywords=("intern",), companies=())
    return Scan(config, database=database, http=fake_http(responses)).run()


def _titles(database: Database) -> list[str]:
    return sorted(posting.title for posting in PostingRepository(database).list_all())


def test_keywords_apply_to_title_and_text(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    result = _scan(database, ACME_RESPONSES)
    assert (result.companies, result.jobs_seen, result.matched, result.added, result.issues) == (1, 5, 2, 2, [])
    assert _titles(database) == ["Backend Engineer", "Software Engineer"]


def test_scanned_postings_are_new_with_platform_source_and_company_name(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _scan(database, ACME_RESPONSES)
    posting = next(p for p in PostingRepository(database).list_all() if p.external_id == "2")
    assert (posting.source, posting.company, posting.status, posting.outcome) == (Source.GREENHOUSE, "Acme", Status.NEW, None)
    assert posting.text == "Our stack: Python."
    assert posting.url == "https://job-boards.greenhouse.io/acme/jobs/2"


# --- dedup rule: UNIQUE(source, external_id); a rescan never duplicates, overwrites or resets a card ------


def test_rescan_adds_nothing_and_keeps_status_outcome_and_note(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    assert _scan(database, ACME_RESPONSES).added == 2
    postings = PostingRepository(database)
    closed = next(p for p in postings.list_all() if p.external_id == "1")
    postings.save(PostingPatch(status=Status.CLOSED, outcome=Outcome.REJECTED, note="no reply").apply_to(closed))

    renamed = {"jobs": [_gh_job(1, "Backend Engineer (renamed)"), *ACME_BOARD["jobs"][1:]]}
    again = _scan(database, {ACME_JOBS: json_response(ACME_JOBS, renamed)})

    assert (again.matched, again.added) == (2, 0)
    assert len(postings.list_all()) == 2
    kept = postings.get(closed.id)
    assert kept is not None
    assert (kept.title, kept.status, kept.outcome, kept.note) == ("Backend Engineer", Status.CLOSED, Outcome.REJECTED, "no reply")


def test_new_job_on_rescan_is_added(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _scan(database, ACME_RESPONSES)
    grown = {"jobs": [*ACME_BOARD["jobs"], _gh_job(6, "Python Developer")]}
    assert _scan(database, {ACME_JOBS: json_response(ACME_JOBS, grown)}).added == 1


def test_same_external_id_on_another_platform_is_a_different_posting(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add_company(database, "Globex", BoardRef(Platform.LEVER, "globex"))
    lever = [{"id": "1", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/globex/1"}]
    result = _scan(database, {**ACME_RESPONSES, GLOBEX_JOBS: json_response(GLOBEX_JOBS, lever)})
    assert result.added == 3
    sources = sorted(posting.source for posting in PostingRepository(database).list_all() if posting.external_id == "1")
    assert sources == [Source.GREENHOUSE, Source.LEVER]


# --- which companies are scanned --------------------------------------------------------------------------


def test_only_verified_enabled_companies_with_a_board_are_scanned(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add_company(database, "Unverified", BoardRef(Platform.GREENHOUSE, "unverified"), verified=False)
    _add_company(database, "Proprietary", None, verified=False)
    _add_company(database, "Disabled", BoardRef(Platform.GREENHOUSE, "disabled"))
    companies = CompanyRepository(database)
    disabled = next(company for company in companies.list_all() if company.name == "Disabled")
    companies.set_enabled(disabled.id, False)
    http = fake_http(ACME_RESPONSES)
    config = AppConfig(db_path=database.path, include_keywords=(), exclude_keywords=(), companies=())
    result = Scan(config, database=database, http=http).run()
    assert result.companies == 1
    assert [call.args[0] for call in http.get.call_args_list] == [ACME_JOBS]


def test_unreadable_boards_are_issues_and_the_scan_continues(database: Database) -> None:
    _add_company(database, "Acme", BoardRef(Platform.GREENHOUSE, "acme"))
    _add_company(database, "Down", BoardRef(Platform.GREENHOUSE, "down"))
    _add_company(database, "Gone", BoardRef(Platform.LEVER, "gone"))
    down = "https://boards-api.greenhouse.io/v1/boards/down/jobs?content=true"
    result = _scan(database, {**ACME_RESPONSES, down: failure(down, 503)})
    assert (result.companies, result.added) == (3, 2)
    messages = {issue.company: issue.message for issue in result.issues}
    assert "HTTP 503" in messages["Down"]
    assert "no longer exists" in messages["Gone"]


def test_no_companies_is_an_empty_result(database: Database) -> None:
    assert _scan(database, {}) == ScanResult(companies=0, jobs_seen=0, matched=0, added=0, issues=[])
