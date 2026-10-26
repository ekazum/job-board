"""HTTP API end to end against a temporary database."""

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from job_board.api.run_routes import RunRoutes
from job_board.app_factory import AppFactory
from job_board.config.app_config import AppConfig
from job_board.models.run_summary import RunSummary
from job_board.models.scan_progress import ScanProgress
from job_board.runs.discover import Discover
from job_board.runs.scan import Scan

DISCOVERED = RunSummary(ok=48, failed=2, duration_s=31.5)
SCANNED = RunSummary(ok=23, failed=0, duration_s=111.8)
SCAN_PROGRESS = ScanProgress(boards_done=23, boards=23, scored=3, to_score=3, duration_s=111.8)

PASTE = {
    "company": "Acme",
    "title": "Backend Engineer",
    "url": "https://www.acme.com/careers/123/?utm_source=linkedin",
    "text": "Build APIs.",
}


def _client(tmp_path: Path, frontend_dist: Path, run_routes: RunRoutes | None = None) -> TestClient:
    config = AppConfig(db_path=tmp_path / "data" / "job_board.db", companies=())
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
        "last_error": None,
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


def test_company_careers_url_is_added_edited_and_cleared(client: TestClient) -> None:
    created = client.post("/api/companies", json={"name": "Acme", "domain": "acme.com", "careers_url": " https://acme.com/jobs "})
    assert (created.status_code, created.json()["careers_url"]) == (201, "https://acme.com/jobs")
    company_id = created.json()["id"]
    edited = client.patch(f"/api/companies/{company_id}", json={"careers_url": "https://acme.com/careers"})
    assert edited.json()["careers_url"] == "https://acme.com/careers"
    toggled = client.patch(f"/api/companies/{company_id}", json={"enabled": False})
    assert (toggled.json()["enabled"], toggled.json()["careers_url"]) == (False, "https://acme.com/careers")
    assert client.patch(f"/api/companies/{company_id}", json={"careers_url": None}).json()["careers_url"] is None
    assert client.patch(f"/api/companies/{company_id}", json={"careers_url": "ftp://acme.com"}).status_code == 422


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


def _fake_runs() -> tuple[MagicMock, MagicMock]:
    """Discover and Scan stand-ins; MagicMock(spec=...) makes their async run() an AsyncMock."""
    discover = MagicMock(spec=Discover)
    discover.run.return_value = DISCOVERED
    scan = MagicMock(spec=Scan)
    scan.run.return_value = SCANNED
    scan.progress = SCAN_PROGRESS
    return discover, scan


def _scan_finished(client: TestClient) -> dict[str, object]:
    """The scan status once the background scan has ended."""
    for _ in range(200):
        status = client.get("/api/scan/status").json()
        if not status["running"]:
            return status
        time.sleep(0.01)
    raise AssertionError("the scan did not end")


def test_discover_returns_ok_failed_and_duration_and_scan_runs_in_the_background(tmp_path: Path) -> None:
    discover, scan = _fake_runs()
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, lambda: scan)) as test_client:
        before = test_client.get("/api/scan/status").json()
        discovered = test_client.post("/api/discover")
        started = test_client.post("/api/scan")
        finished = _scan_finished(test_client)
    assert (before["running"], before["boards"], before["error"]) == (False, 0, None)
    assert (discovered.status_code, discovered.json()) == (200, {"ok": 48, "failed": 2, "duration_s": 31.5})
    assert (started.status_code, started.json()["running"]) == (202, True)
    assert finished == {**SCAN_PROGRESS.model_dump(), "running": False, "error": None}
    discover.run.assert_awaited_once_with()
    scan.run.assert_awaited_once_with()


def test_each_run_gets_a_fresh_orchestrator(tmp_path: Path) -> None:
    discover, scan = _fake_runs()
    factory = MagicMock(return_value=scan)
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, factory)) as test_client:
        test_client.post("/api/scan")
        _scan_finished(test_client)
        test_client.post("/api/scan")
        _scan_finished(test_client)
    assert factory.call_count == 2


def test_a_scan_that_fails_reports_why(tmp_path: Path) -> None:
    discover, scan = _fake_runs()
    scan.run.side_effect = RuntimeError("database is locked")
    with _client(tmp_path, tmp_path / "no-dist", RunRoutes(lambda: discover, lambda: scan)) as test_client:
        test_client.post("/api/scan")
        finished = _scan_finished(test_client)
    assert finished["error"] == "RuntimeError: database is locked"


@pytest.mark.anyio
async def test_second_run_while_one_is_in_progress_is_409(tmp_path: Path) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_discover() -> RunSummary:
        started.set()
        await release.wait()
        return DISCOVERED

    discover, scan = _fake_runs()
    discover.run.side_effect = slow_discover
    config = AppConfig(db_path=tmp_path / "x.db", companies=())
    app = AppFactory(lambda: config, tmp_path / "no-dist", run_routes=RunRoutes(lambda: discover, lambda: scan)).build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/discover"))
        await started.wait()
        busy = await client.post("/api/scan")
        release.set()
        finished = await first
        after = await client.post("/api/scan")
        while (await client.get("/api/scan/status")).json()["running"]:
            await asyncio.sleep(0.01)
    assert (busy.status_code, finished.status_code, after.status_code) == (409, 200, 202)
    assert "already in progress" in busy.json()["detail"]
    scan.run.assert_awaited_once_with()


@pytest.mark.anyio
async def test_nothing_else_runs_while_a_scan_is_in_progress(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def slow_scan() -> RunSummary:
        await release.wait()
        return SCANNED

    discover, scan = _fake_runs()
    scan.run.side_effect = slow_scan
    config = AppConfig(db_path=tmp_path / "x.db", companies=())
    app = AppFactory(lambda: config, tmp_path / "no-dist", run_routes=RunRoutes(lambda: discover, lambda: scan)).build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        started = await client.post("/api/scan")
        busy = [(await client.post("/api/scan")).status_code, (await client.post("/api/discover")).status_code]
        running = (await client.get("/api/scan/status")).json()["running"]
        release.set()
        while (await client.get("/api/scan/status")).json()["running"]:
            await asyncio.sleep(0.01)
    assert (started.status_code, busy, running) == (202, [409, 409], True)
    discover.run.assert_not_awaited()


def test_openapi_uses_method_names_as_operation_ids(client: TestClient) -> None:
    operations = {
        operation["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for operation in path.values()
    }
    assert operations == {
        "list_postings",
        "posting_facets",
        "create_posting",
        "get_posting",
        "patch_posting",
        "chat",
        "resume_chat",
        "chat_history",
        "delete_chat",
        "purge_rejects",
        "list_companies",
        "create_company",
        "patch_company",
        "run_discover",
        "run_scan",
        "scan_status",
        "get_llm_settings",
        "set_llm_provider",
        "test_llm",
        "get_profile",
        "upload_profile",
        "patch_profile",
        "start_rescore",
        "rescore_status",
        "apply_filters",
        "rescore_posting",
    }
