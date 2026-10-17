"""HTTP API end to end against a temporary database."""

import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from job_board.app_config import AppConfig
from job_board.app_factory import AppFactory
from job_board.discover import Discover
from job_board.models.discover_result import DiscoverResult
from job_board.models.run_issue import RunIssue
from job_board.models.scan_result import ScanResult
from job_board.run_routes import RunRoutes
from job_board.scan import Scan

DISCOVERED = DiscoverResult(
    companies=3, verified=1, unverified=1, no_platform=0, issues=[RunIssue(company="Initech", message="offline")]
)
SCANNED = ScanResult(companies=1, jobs_seen=40, matched=3, added=2, issues=[])

PASTE = {
    "company": "Acme",
    "title": "Backend Engineer",
    "url": "https://www.acme.com/careers/123/?utm_source=linkedin",
    "text": "Build APIs.",
}


def _client(tmp_path: Path, frontend_dist: Path, run_routes: RunRoutes | None = None) -> TestClient:
    config = AppConfig(db_path=tmp_path / "data" / "job_board.db", include_keywords=(), exclude_keywords=(), companies=())
    return TestClient(AppFactory(lambda: config, frontend_dist, run_routes=run_routes).build())


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _client(tmp_path, tmp_path / "no-dist") as test_client:
        yield test_client


def _paste(client: TestClient, **overrides: str) -> int:
    response = client.post("/api/postings", json={**PASTE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- postings ---------------------------------------------------------------------------------------------


def test_paste_creates_manual_posting_with_canonical_external_id(client: TestClient) -> None:
    response = client.post("/api/postings", json=PASTE)
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "manual"
    assert body["external_id"] == "https://acme.com/careers/123"
    assert body["url"] == PASTE["url"]
    assert (body["status"], body["outcome"], body["note"], body["text"]) == ("new", None, "", "Build APIs.")


def test_paste_same_job_again_returns_existing_with_200(client: TestClient) -> None:
    posting_id = _paste(client)
    client.patch(f"/api/postings/{posting_id}", json={"status": "applied"})
    again = client.post("/api/postings", json={**PASTE, "url": "https://acme.com/careers/123#top", "title": "Other"})
    assert again.status_code == 200
    assert (again.json()["id"], again.json()["status"], again.json()["title"]) == (posting_id, "applied", PASTE["title"])
    assert len(client.get("/api/postings").json()) == 1


@pytest.mark.parametrize(
    "overrides",
    [{"url": "acme.com/jobs/1"}, {"url": "javascript:alert(1)"}, {"title": "   "}, {"company": ""}],
)
def test_paste_rejects_bad_input(client: TestClient, overrides: dict[str, str]) -> None:
    assert client.post("/api/postings", json={**PASTE, **overrides}).status_code == 422


def test_paste_text_is_optional(client: TestClient) -> None:
    payload = {key: value for key, value in PASTE.items() if key != "text"}
    assert client.post("/api/postings", json=payload).json()["text"] == ""


def test_list_is_newest_first(client: TestClient) -> None:
    first = _paste(client, url="https://acme.com/jobs/1")
    second = _paste(client, url="https://acme.com/jobs/2")
    assert [posting["id"] for posting in client.get("/api/postings").json()] == [second, first]


def test_move_between_columns(client: TestClient) -> None:
    posting_id = _paste(client)
    for status in ("applied", "interview", "new"):
        response = client.patch(f"/api/postings/{posting_id}", json={"status": status})
        assert (response.status_code, response.json()["status"]) == (200, status)


def test_close_with_outcome_then_reopen_clears_it(client: TestClient) -> None:
    posting_id = _paste(client)
    closed = client.patch(f"/api/postings/{posting_id}", json={"status": "closed", "outcome": "rejected"})
    assert (closed.json()["status"], closed.json()["outcome"]) == ("closed", "rejected")
    reopened = client.patch(f"/api/postings/{posting_id}", json={"status": "interview"})
    assert (reopened.json()["status"], reopened.json()["outcome"]) == ("interview", None)


def test_outcome_rule_violations_are_422(client: TestClient) -> None:
    posting_id = _paste(client)
    paired = client.patch(f"/api/postings/{posting_id}", json={"status": "applied", "outcome": "offer"})
    alone = client.patch(f"/api/postings/{posting_id}", json={"outcome": "offer"})
    assert (paired.status_code, alone.status_code) == (422, 422)
    assert "only when status is 'closed'" in alone.json()["detail"]
    assert client.get("/api/postings").json()[0]["outcome"] is None


def test_note_update_keeps_status(client: TestClient) -> None:
    posting_id = _paste(client)
    client.patch(f"/api/postings/{posting_id}", json={"status": "closed", "outcome": "offer"})
    response = client.patch(f"/api/postings/{posting_id}", json={"note": "Start in January"})
    assert (response.json()["note"], response.json()["status"], response.json()["outcome"]) == (
        "Start in January",
        "closed",
        "offer",
    )


def test_patch_unknown_posting_is_404(client: TestClient) -> None:
    assert client.patch("/api/postings/999", json={"status": "applied"}).status_code == 404


def test_patch_unknown_status_is_422(client: TestClient) -> None:
    posting_id = _paste(client)
    assert client.patch(f"/api/postings/{posting_id}", json={"status": "archived"}).status_code == 422


# --- companies --------------------------------------------------------------------------------------------


def test_company_create_list_and_duplicate(client: TestClient) -> None:
    created = client.post("/api/companies", json={"name": "Acme"})
    assert created.status_code == 201
    assert created.json() | {"id": 0} == {
        "id": 0,
        "name": "Acme",
        "domain": None,
        "careers_url": None,
        "platform": None,
        "slug": None,
        "verified": False,
        "enabled": True,
        "last_checked": None,
    }
    duplicate = client.post("/api/companies", json={"name": " acme "})
    assert (duplicate.status_code, duplicate.json()["id"], duplicate.json()["name"]) == (200, created.json()["id"], "Acme")
    client.post("/api/companies", json={"name": "Beta"})
    assert [company["name"] for company in client.get("/api/companies").json()] == ["Acme", "Beta"]


def test_company_domain_is_stored_bare(client: TestClient) -> None:
    created = client.post("/api/companies", json={"name": "Acme", "domain": " https://www.Acme.com/careers "})
    assert (created.status_code, created.json()["domain"]) == (201, "acme.com")
    assert client.post("/api/companies", json={"name": "Blank", "domain": ""}).json()["domain"] is None


def test_company_invalid_domain_is_422(client: TestClient) -> None:
    response = client.post("/api/companies", json={"name": "Acme", "domain": "localhost"})
    assert response.status_code == 422
    assert "not a domain" in response.text


def test_company_toggle_enabled(client: TestClient) -> None:
    company_id = client.post("/api/companies", json={"name": "Acme"}).json()["id"]
    assert client.patch(f"/api/companies/{company_id}", json={"enabled": False}).json()["enabled"] is False
    assert client.patch(f"/api/companies/{company_id}", json={}).json()["enabled"] is False
    assert client.patch(f"/api/companies/{company_id}", json={"enabled": True}).json()["enabled"] is True


def test_company_errors(client: TestClient) -> None:
    assert client.post("/api/companies", json={"name": "  "}).status_code == 422
    assert client.patch("/api/companies/999", json={"enabled": False}).status_code == 404


# --- app --------------------------------------------------------------------------------------------------


def test_frontend_served_at_root_without_shadowing_api(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>job-board</title>", encoding="utf-8")
    with _client(tmp_path, dist) as test_client:
        assert "job-board" in test_client.get("/").text
        assert test_client.get("/api/postings").json() == []


def _fake_runs(discover_result: DiscoverResult = DISCOVERED, scan_result: ScanResult = SCANNED) -> tuple[MagicMock, MagicMock]:
    discover = MagicMock(spec=Discover)
    discover.run.return_value = discover_result
    scan = MagicMock(spec=Scan)
    scan.run.return_value = scan_result
    return discover, scan


def test_discover_and_scan_return_counts(tmp_path: Path) -> None:
    discover, scan = _fake_runs()
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, lambda: scan)) as test_client:
        discovered = test_client.post("/api/discover")
        scanned = test_client.post("/api/scan")
    assert (discovered.status_code, discovered.json()) == (200, DISCOVERED.model_dump())
    assert (scanned.status_code, scanned.json()) == (200, SCANNED.model_dump())
    discover.run.assert_called_once_with()
    scan.run.assert_called_once_with()


def test_each_run_gets_a_fresh_orchestrator(tmp_path: Path) -> None:
    discover, scan = _fake_runs()
    factory = MagicMock(return_value=scan)
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, factory)) as test_client:
        test_client.post("/api/scan")
        test_client.post("/api/scan")
    assert factory.call_count == 2


def test_second_run_while_one_is_in_progress_is_409(tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()

    def slow_discover() -> DiscoverResult:
        started.set()
        release.wait(timeout=5)
        return DISCOVERED

    discover, scan = _fake_runs()
    discover.run.side_effect = slow_discover
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, lambda: scan)) as test_client:
        first: dict[str, int] = {}
        worker = threading.Thread(target=lambda: first.update(status=test_client.post("/api/discover").status_code))
        worker.start()
        assert started.wait(timeout=5)
        busy = test_client.post("/api/scan")
        release.set()
        worker.join(timeout=5)
        after = test_client.post("/api/scan")
    assert (busy.status_code, first["status"], after.status_code) == (409, 200, 200)
    assert "already in progress" in busy.json()["detail"]
    scan.run.assert_called_once_with()


def test_openapi_uses_method_names_as_operation_ids(client: TestClient) -> None:
    operations = {
        operation["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for operation in path.values()
    }
    assert operations == {
        "list_postings",
        "create_posting",
        "patch_posting",
        "list_companies",
        "create_company",
        "patch_company",
        "run_discover",
        "run_scan",
    }
