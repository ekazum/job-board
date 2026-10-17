"""Discover: careers-page links, API verification, domain-stem probing, upsert into companies."""

from collections.abc import Mapping
from pathlib import Path

from job_board.app_config import AppConfig
from job_board.company_repository import CompanyRepository
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.discover import Discover
from job_board.enums.platform import Platform
from job_board.http_response import HttpResponse
from job_board.models.company import Company
from job_board.models.discover_result import DiscoverResult

from tests.http_fakes import failure, fake_http, json_response, page, requested_urls

GH_API = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
LEVER_PROBE = "https://api.lever.co/v0/postings/{}?mode=json&limit=1"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{}"


def _config(database: Database, *seeds: CompanySeed) -> AppConfig:
    return AppConfig(db_path=database.path, include_keywords=(), exclude_keywords=(), companies=seeds)


def _run(database: Database, responses: Mapping[str, HttpResponse], *seeds: CompanySeed) -> DiscoverResult:
    return Discover(_config(database, *seeds), database=database, http=fake_http(responses)).run()


def _company(database: Database, name: str) -> Company:
    return next(company for company in CompanyRepository(database).list_all() if company.name == name)


def test_greenhouse_embed_on_careers_page_is_verified(database: Database) -> None:
    careers = "https://acme.com/careers"
    responses = {
        careers: page(careers, '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmeinc"></script>'),
        GH_API.format("acmeinc"): json_response(GH_API.format("acmeinc"), {"jobs": []}),
    }
    result = _run(database, responses, CompanySeed("Acme", "acme.com"))
    assert (result.companies, result.verified, result.unverified, result.no_platform, result.issues) == (1, 1, 0, 0, [])
    company = _company(database, "Acme")
    assert (company.platform, company.slug, company.verified, company.careers_url) == (Platform.GREENHOUSE, "acmeinc", True, careers)
    assert company.domain == "acme.com"
    assert company.last_checked is not None


def test_redirect_to_board_is_found_from_final_url(database: Database) -> None:
    jobs = "https://acme.com/jobs"
    responses = {
        jobs: page(jobs, "<html>Loading...</html>", final_url="https://jobs.lever.co/acme"),
        LEVER_PROBE.format("acme"): json_response(LEVER_PROBE.format("acme"), [{"id": "x"}]),
    }
    result = _run(database, responses, CompanySeed("Acme", "acme.com"))
    assert result.verified == 1
    assert (_company(database, "Acme").platform, _company(database, "Acme").careers_url) == (Platform.LEVER, "https://jobs.lever.co/acme")


def test_link_whose_api_does_not_confirm_is_stored_unverified(database: Database) -> None:
    careers = "https://acme.com/careers"
    result = _run(database, {careers: page(careers, '<a href="https://jobs.ashbyhq.com/acme-old">')}, CompanySeed("Acme", "acme.com"))
    assert (result.verified, result.unverified) == (0, 1)
    company = _company(database, "Acme")
    assert (company.platform, company.slug, company.verified) == (Platform.ASHBY, "acme-old", False)


def test_configured_careers_url_is_fetched_first(database: Database) -> None:
    custom = "https://acme.com/about/work-with-us"
    http = fake_http({custom: page(custom, '<a href="https://jobs.lever.co/acme">')})
    Discover(_config(database, CompanySeed("Acme", "acme.com", custom)), database=database, http=http).run()
    assert requested_urls(http)[0] == custom
    assert "https://acme.com/careers" not in requested_urls(http)


def test_no_link_falls_back_to_domain_stem_probe(database: Database) -> None:
    responses = {ASHBY_API.format("globex"): json_response(ASHBY_API.format("globex"), {"jobs": [], "apiVersion": "1"})}
    http = fake_http(responses)
    result = Discover(_config(database, CompanySeed("Globex", "globex.co.il")), database=database, http=http).run()
    assert result.verified == 1
    company = _company(database, "Globex")
    assert (company.platform, company.slug, company.verified) == (Platform.ASHBY, "globex", True)
    assert requested_urls(http) == [
        "https://globex.co.il/careers",
        "https://globex.co.il/jobs",
        "https://globex.co.il/join-us",
        GH_API.format("globex"),
        LEVER_PROBE.format("globex"),
        ASHBY_API.format("globex"),
    ]


def test_guessed_greenhouse_board_of_another_company_is_rejected(database: Database) -> None:
    gh, board = GH_API.format("orca"), "https://boards-api.greenhouse.io/v1/boards/orca"
    responses = {
        gh: json_response(gh, {"jobs": [{"id": 1}]}),
        board: json_response(board, {"name": "ORCA Service Technologies"}),
    }
    http = fake_http(responses)
    result = Discover(_config(database, CompanySeed("Orca Security", "orca.security")), database=database, http=http).run()
    assert (result.verified, result.no_platform) == (0, 1)
    assert _company(database, "Orca Security").platform == Platform.NONE
    assert LEVER_PROBE.format("orca") in requested_urls(http)  # kept probing the other platforms


def test_guessed_greenhouse_board_with_matching_name_is_accepted(database: Database) -> None:
    gh, board = GH_API.format("ridewithvia"), "https://boards-api.greenhouse.io/v1/boards/ridewithvia"
    responses = {gh: json_response(gh, {"jobs": []}), board: json_response(board, {"name": "Via Transportation"})}
    result = _run(database, responses, CompanySeed("Via", "ridewithvia.com"))
    assert result.verified == 1


def test_board_link_on_the_company_site_skips_the_name_check(database: Database) -> None:
    careers, gh = "https://orca.security/careers", GH_API.format("orca")
    board = "https://boards-api.greenhouse.io/v1/boards/orca"
    responses = {
        careers: page(careers, '<a href="https://boards.greenhouse.io/orca">'),
        gh: json_response(gh, {"jobs": []}),
        board: json_response(board, {"name": "Something Else"}),
    }
    assert _run(database, responses, CompanySeed("Orca Security", "orca.security")).verified == 1


def test_nothing_found_is_platform_none(database: Database) -> None:
    result = _run(database, {}, CompanySeed("Initech", "initech.io"))
    assert (result.no_platform, result.verified) == (1, 0)
    company = _company(database, "Initech")
    assert (company.platform, company.slug, company.verified) == (Platform.NONE, None, False)


def test_unreachable_probes_are_an_issue_and_keep_the_previous_row(database: Database) -> None:
    gh = GH_API.format("acme")
    _run(database, {gh: json_response(gh, {"jobs": []})}, CompanySeed("Acme", "acme.com"))
    offline = {url: failure(url) for url in (gh, LEVER_PROBE.format("acme"), ASHBY_API.format("acme"))}
    result = _run(database, offline, CompanySeed("Acme", "acme.com"))
    assert (result.companies, result.verified, result.no_platform) == (1, 0, 0)
    assert [issue.company for issue in result.issues] == ["Acme"]
    assert "offline" in result.issues[0].message
    assert (_company(database, "Acme").platform, _company(database, "Acme").verified) == (Platform.GREENHOUSE, True)


def test_rediscovery_updates_board_but_keeps_enabled_flag(database: Database) -> None:
    gh = GH_API.format("acme")
    _run(database, {gh: json_response(gh, {"jobs": []})}, CompanySeed("Acme", "acme.com"))
    repository = CompanyRepository(database)
    repository.set_enabled(_company(database, "Acme").id, False)
    lever = LEVER_PROBE.format("acme")
    _run(database, {lever: json_response(lever, [])}, CompanySeed("acme", "acme.com"))  # same company, other case
    companies = repository.list_all()
    assert len(companies) == 1
    assert (companies[0].platform, companies[0].enabled) == (Platform.LEVER, False)


def test_companies_added_in_the_ui_with_a_domain_are_discovered(database: Database) -> None:
    repository = CompanyRepository(database)
    repository.insert("Globex", "globex.com")
    repository.insert("NoDomain")
    gh_acme, gh_globex = GH_API.format("acme"), GH_API.format("globex")
    responses = {gh_acme: json_response(gh_acme, {"jobs": []}), gh_globex: json_response(gh_globex, {"jobs": []})}
    result = _run(database, responses, CompanySeed("Acme", "acme.com"))
    assert (result.companies, result.verified) == (2, 2)
    assert (_company(database, "Globex").platform, _company(database, "NoDomain").platform) == (Platform.GREENHOUSE, None)


def test_config_entry_wins_over_stored_company_with_the_same_name(database: Database) -> None:
    CompanyRepository(database).insert("Acme", "old-acme.com")
    http = fake_http({})
    Discover(_config(database, CompanySeed("ACME", "acme.com")), database=database, http=http).run()
    urls = requested_urls(http)
    assert "https://acme.com/careers" in urls
    assert not any("old-acme.com" in url for url in urls)
    assert _company(database, "Acme").domain == "acme.com"


def test_counts_across_several_companies(tmp_path: Path) -> None:
    database = Database(tmp_path / "x.db")
    gh = GH_API.format("acme")
    responses = {
        gh: json_response(gh, {"jobs": []}),
        "https://globex.com/careers": page("https://globex.com/careers", '<a href="https://jobs.lever.co/gone">'),
    }
    result = _run(database, responses, CompanySeed("Acme", "acme.com"), CompanySeed("Globex", "globex.com"), CompanySeed("Initech", "initech.com"))
    assert (result.companies, result.verified, result.unverified, result.no_platform) == (3, 1, 1, 1)
