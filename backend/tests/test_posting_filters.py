"""Filter bar: GET /api/postings query parameters (filtered in SQL) and GET /api/postings/facets."""

from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_board.app_config import AppConfig
from job_board.app_factory import AppFactory
from job_board.database import Database
from job_board.enums.source import Source
from job_board.posting_repository import PostingRepository

ROWS: list[tuple[Source, str, str, str, int | None]] = [
    (Source.GREENHOUSE, "Acme", "Senior AI Engineer", "Build LLM agents.", 9),
    (Source.GREENHOUSE, "Acme", "Security Researcher", "Threat research.", 4),
    (Source.LEVER, "Globex", "ML Engineer", "Train models with 100% coverage_of tests.", None),
    (Source.WORKDAY, "Initech", "Chief Architect", "Platform architecture; LLM roadmap.", 7),
]


def _seed(database: Database) -> None:
    postings = PostingRepository(database)
    for index, (source, company, title, text, fit) in enumerate(ROWS):
        posting, _ = postings.insert(source=source, external_id=str(index), company=company, title=title, url=f"https://x/{index}", text=text)
        with closing(database.connect()) as connection, connection:
            connection.execute("UPDATE postings SET fit = :fit WHERE id = :id", {"fit": fit, "id": posting.id})
    first = postings.list_all()[-1]
    postings.save(first.model_copy(update={"status": "applied"}))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    config = AppConfig(db_path=tmp_path / "data" / "job_board.db", include_keywords=(), exclude_keywords=(), companies=())
    with TestClient(AppFactory(lambda: config, tmp_path / "no-dist").build()) as test_client:
        _seed(Database(config.db_path))
        yield test_client


def _titles(client: TestClient, query: str = "") -> list[str]:
    return sorted(posting["title"] for posting in client.get(f"/api/postings{query}").json())


def test_no_parameters_returns_everything(client: TestClient) -> None:
    assert len(_titles(client)) == 4


def test_q_is_a_case_insensitive_title_substring(client: TestClient) -> None:
    assert _titles(client, "?q=engineer") == ["ML Engineer", "Senior AI Engineer"]
    assert _titles(client, "?q=LLM") == []  # only in descriptions


def test_in_text_also_searches_descriptions(client: TestClient) -> None:
    assert _titles(client, "?q=llm&in_text=true") == ["Chief Architect", "Senior AI Engineer"]


def test_like_wildcards_in_q_are_literal(client: TestClient) -> None:
    assert _titles(client, "?q=100%25&in_text=true") == ["ML Engineer"]
    assert _titles(client, "?q=coverage_of&in_text=true") == ["ML Engineer"]
    assert _titles(client, "?q=_&in_text=false") == []  # "_" is not "any character"


def test_company_and_source_are_repeatable(client: TestClient) -> None:
    assert _titles(client, "?company=Globex&company=Initech") == ["Chief Architect", "ML Engineer"]
    assert _titles(client, "?source=greenhouse") == ["Security Researcher", "Senior AI Engineer"]
    assert _titles(client, "?company=Acme&source=lever") == []


def test_min_fit_keeps_unscored_postings(client: TestClient) -> None:
    assert _titles(client, "?min_fit=7") == ["Chief Architect", "ML Engineer", "Senior AI Engineer"]
    assert client.get("/api/postings?min_fit=11").status_code == 422


def test_filters_combine(client: TestClient) -> None:
    assert _titles(client, "?q=engineer&company=Acme&min_fit=5") == ["Senior AI Engineer"]


def test_unknown_source_is_422(client: TestClient) -> None:
    assert client.get("/api/postings?source=linkedin").status_code == 422


def test_facets_list_companies_sources_and_unfiltered_totals(client: TestClient) -> None:
    facets = client.get("/api/postings/facets").json()
    assert facets["companies"] == ["Acme", "Globex", "Initech"]
    assert facets["sources"] == ["greenhouse", "lever", "workday"]
    assert facets["totals"] == {"new": 3, "applied": 1, "interview": 0, "closed": 0}


def test_postings_carry_fit(client: TestClient) -> None:
    fits = {posting["title"]: posting["fit"] for posting in client.get("/api/postings").json()}
    assert (fits["Senior AI Engineer"], fits["ML Engineer"]) == (9, None)


def test_archive_holds_scorer_rejects_and_is_left_out_of_the_board(client: TestClient, tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "job_board.db")
    with closing(database.connect()) as connection, connection:
        connection.execute("UPDATE postings SET status = 'closed', outcome = 'not_relevant' WHERE title = 'Security Researcher'")
    board = _titles(client)
    archive = _titles(client, "?archived=true")
    assert "Security Researcher" not in board and archive == ["Security Researcher"]
    assert client.get("/api/postings/facets").json()["totals"]["closed"] == 0  # not counted on the board


def _set(database: Database, title: str, **columns: object) -> None:
    assignments = ", ".join(f"{column} = :{column}" for column in columns)
    with closing(database.connect()) as connection, connection:
        connection.execute(f"UPDATE postings SET {assignments} WHERE title = :title", {**columns, "title": title})


def test_location_is_a_substring_with_spellings_normalized(client: TestClient, tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "job_board.db")
    _set(database, "Senior AI Engineer", location="Tel Aviv-Yafo, Israel")
    _set(database, "ML Engineer", location="Petach Tikva")
    assert _titles(client, "?location=tel-aviv") == ["Senior AI Engineer"]
    assert _titles(client, "?location=Petah%20Tikva") == ["ML Engineer"]
    assert _titles(client, "?location=israel&q=senior") == ["Senior AI Engineer"]


def test_archive_holds_location_rejects_and_purge_deletes_only_them(client: TestClient, tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "job_board.db")
    _set(database, "Security Researcher", status="closed", outcome="not_relevant", fit_reason="location: Berlin")
    _set(database, "ML Engineer", status="closed", outcome="not_relevant", fit=2, fit_reason="far off")  # the scorer's
    assert _titles(client, "?archived=true") == ["ML Engineer", "Security Researcher"]
    assert client.delete("/api/postings/location-rejects").json() == {"deleted": 1}
    assert _titles(client, "?archived=true") == ["ML Engineer"]
    assert len(_titles(client)) == 2
