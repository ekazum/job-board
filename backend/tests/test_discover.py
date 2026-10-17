"""Discover: careers-page links, API verification, domain-stem probing, upsert and per-company errors."""

from pathlib import Path

import pytest

from job_board.app_config import AppConfig
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.discover import Discover
from job_board.enums.platform import Platform
from job_board.models.company import Company
from job_board.models.run_summary import RunSummary

from tests.http_fakes import FakeWeb

GH_API = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
GH_BOARD = "https://boards-api.greenhouse.io/v1/boards/{}"
LEVER_PROBE = "https://api.lever.co/v0/postings/{}?mode=json&limit=1"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{}"
WORKDAY_JOBS = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"


def _config(database: Database, *seeds: CompanySeed) -> AppConfig:
    return AppConfig(db_path=database.path, include_keywords=(), exclude_keywords=(), companies=seeds)


async def _run(database: Database, web: FakeWeb, *seeds: CompanySeed) -> RunSummary:
    async with web.client() as http:
        return await Discover(_config(database, *seeds), database=database, http=http).run()


def _company(database: Database, name: str) -> Company:
    return next(company for company in CompanyRepository(database).list_all() if company.name == name)


@pytest.mark.anyio
async def test_greenhouse_embed_on_careers_page_is_verified(database: Database) -> None:
    web = FakeWeb()
    web.page("https://acme.com/careers", '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmeinc"></script>')
    web.json(GH_API.format("acmeinc"), {"jobs": []})
    summary = await _run(database, web, CompanySeed("Acme", "acme.com"))
    assert (summary.ok, summary.failed) == (1, 0)
    company = _company(database, "Acme")
    assert (company.platform, company.slug, company.verified) == (Platform.GREENHOUSE, "acmeinc", True)
    assert (company.careers_url, company.last_error, company.domain) == ("https://acme.com/careers", None, "acme.com")


@pytest.mark.anyio
async def test_redirect_to_board_is_found_from_final_url(database: Database) -> None:
    web = FakeWeb()
    web.redirect("https://acme.com/jobs", "https://jobs.lever.co/acme")
    web.page("https://jobs.lever.co/acme", "<html>Loading...</html>")
    web.json(LEVER_PROBE.format("acme"), [{"id": "x"}])
    await _run(database, web, CompanySeed("Acme", "acme.com"))
    assert (_company(database, "Acme").platform, _company(database, "Acme").verified) == (Platform.LEVER, True)


@pytest.mark.anyio
async def test_all_candidate_pages_are_fetched_and_the_first_in_order_wins(database: Database) -> None:
    web = FakeWeb()
    web.page("https://acme.com/about/careers", '<a href="https://jobs.lever.co/acme-configured">')
    web.page("https://acme.com/careers", '<a href="https://boards.greenhouse.io/acme-fallback">')
    web.json(LEVER_PROBE.format("acme-configured"), [])
    await _run(database, web, CompanySeed("Acme", "acme.com", "https://acme.com/about/careers"))
    assert _company(database, "Acme").slug == "acme-configured"  # careers_url beats /careers
    assert {"https://acme.com/careers", "https://acme.com/jobs", "https://acme.com/join-us"} <= set(web.urls())


@pytest.mark.anyio
async def test_link_whose_api_does_not_confirm_is_stored_unverified(database: Database) -> None:
    web = FakeWeb()
    web.page("https://acme.com/careers", '<a href="https://jobs.ashbyhq.com/acme-old">')
    summary = await _run(database, web, CompanySeed("Acme", "acme.com"))
    company = _company(database, "Acme")
    assert (summary.ok, company.platform, company.slug, company.verified) == (1, Platform.ASHBY, "acme-old", False)


@pytest.mark.anyio
async def test_workday_link_stores_tenant_host_and_site(database: Database) -> None:
    web = FakeWeb()
    web.page("https://nvidia.com/careers", '<a href="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite">')
    web.json(WORKDAY_JOBS, {"total": 1, "jobPostings": []}, method="POST")
    await _run(database, web, CompanySeed("Nvidia", "nvidia.com"))
    company = _company(database, "Nvidia")
    assert (company.platform, company.slug, company.verified) == (Platform.WORKDAY, "nvidia/NVIDIAExternalCareerSite", True)
    target = CompanyRepository(database).list_scannable()[0]
    assert (target.board.tenant, target.board.wd_host, target.board.site) == ("nvidia", "wd5", "NVIDIAExternalCareerSite")


@pytest.mark.anyio
async def test_no_link_falls_back_to_domain_stem_probe(database: Database) -> None:
    web = FakeWeb()
    web.json(ASHBY_API.format("globex"), {"jobs": [], "apiVersion": "1"})
    await _run(database, web, CompanySeed("Globex", "globex.co.il"))
    company = _company(database, "Globex")
    assert (company.platform, company.slug, company.verified) == (Platform.ASHBY, "globex", True)
    assert {GH_API.format("globex"), LEVER_PROBE.format("globex"), ASHBY_API.format("globex")} <= set(web.urls())


@pytest.mark.anyio
async def test_guessed_greenhouse_board_of_another_company_is_rejected(database: Database) -> None:
    web = FakeWeb()
    web.json(GH_API.format("orca"), {"jobs": [{"id": 1}]})
    web.json(GH_BOARD.format("orca"), {"name": "ORCA Service Technologies"})
    await _run(database, web, CompanySeed("Orca Security", "orca.security"))
    assert _company(database, "Orca Security").platform == Platform.NONE


@pytest.mark.anyio
async def test_guessed_greenhouse_board_with_matching_name_is_accepted(database: Database) -> None:
    web = FakeWeb()
    web.json(GH_API.format("ridewithvia"), {"jobs": []})
    web.json(GH_BOARD.format("ridewithvia"), {"name": "Via Transportation"})
    await _run(database, web, CompanySeed("Via", "ridewithvia.com"))
    assert _company(database, "Via").verified is True


@pytest.mark.anyio
async def test_nothing_found_is_platform_none(database: Database) -> None:
    summary = await _run(database, FakeWeb(), CompanySeed("Initech", "initech.io"))
    company = _company(database, "Initech")
    assert (summary.ok, company.platform, company.slug, company.verified) == (1, Platform.NONE, None, False)


@pytest.mark.anyio
async def test_unreachable_boards_record_last_error_and_keep_the_previous_board(database: Database) -> None:
    web = FakeWeb()
    web.json(GH_API.format("acme"), {"jobs": []})
    await _run(database, web, CompanySeed("Acme", "acme.com"))
    offline = FakeWeb()
    for url in (GH_API.format("acme"), LEVER_PROBE.format("acme"), ASHBY_API.format("acme")):
        offline.timeout(url)
    summary = await _run(database, offline, CompanySeed("Acme", "acme.com"))
    company = _company(database, "Acme")
    assert (summary.ok, summary.failed) == (0, 1)
    assert (company.platform, company.verified) == (Platform.GREENHOUSE, True)
    assert company.last_error is not None and "timeout" in company.last_error


@pytest.mark.anyio
async def test_a_failing_company_does_not_stop_the_others(database: Database) -> None:
    web = FakeWeb()
    web.status(GH_API.format("down"), 503)
    web.json(GH_API.format("acme"), {"jobs": []})
    summary = await _run(database, web, CompanySeed("Down", "down.com"), CompanySeed("Acme", "acme.com"))
    assert (summary.ok, summary.failed) == (1, 1)
    assert _company(database, "Acme").verified is True
    assert "HTTP 503" in (_company(database, "Down").last_error or "")


@pytest.mark.anyio
async def test_rediscovery_updates_board_but_keeps_enabled_flag(database: Database) -> None:
    web = FakeWeb()
    web.json(GH_API.format("acme"), {"jobs": []})
    await _run(database, web, CompanySeed("Acme", "acme.com"))
    repository = CompanyRepository(database)
    repository.set_enabled(_company(database, "Acme").id, False)
    moved = FakeWeb()
    moved.json(LEVER_PROBE.format("acme"), [])
    await _run(database, moved, CompanySeed("acme", "acme.com"))  # same company, other case
    companies = repository.list_all()
    assert len(companies) == 1
    assert (companies[0].platform, companies[0].enabled) == (Platform.LEVER, False)


@pytest.mark.anyio
async def test_companies_added_in_the_ui_are_discovered_with_their_careers_url(database: Database) -> None:
    CompanyRepository(database).insert("Globex", "globex.com", "https://globex.com/work-with-us")
    CompanyRepository(database).insert("NoDomain")
    web = FakeWeb()
    web.page("https://globex.com/work-with-us", '<a href="https://jobs.lever.co/globex">')
    web.json(LEVER_PROBE.format("globex"), [])
    web.json(GH_API.format("acme"), {"jobs": []})
    summary = await _run(database, web, CompanySeed("Acme", "acme.com"))
    assert summary.ok == 2
    assert (_company(database, "Globex").platform, _company(database, "NoDomain").platform) == (Platform.LEVER, None)


@pytest.mark.anyio
async def test_stored_careers_url_is_used_when_config_has_none(database: Database) -> None:
    CompanyRepository(database).insert("Acme", "acme.com", "https://acme.com/team")
    web = FakeWeb()
    web.page("https://acme.com/team", '<a href="https://jobs.lever.co/acme">')
    web.json(LEVER_PROBE.format("acme"), [])
    await _run(database, web, CompanySeed("Acme", "acme.com"))
    assert (_company(database, "Acme").platform, _company(database, "Acme").careers_url) == (Platform.LEVER, "https://acme.com/team")


@pytest.mark.anyio
async def test_summary_counts_and_duration(tmp_path: Path) -> None:
    database = Database(tmp_path / "x.db")
    web = FakeWeb()
    web.json(GH_API.format("acme"), {"jobs": []})
    web.status(GH_API.format("down"), 500)
    summary = await _run(database, web, CompanySeed("Acme", "acme.com"), CompanySeed("Down", "down.com"), CompanySeed("Initech", "initech.com"))
    assert (summary.ok, summary.failed) == (2, 1)
    assert summary.duration_s >= 0
