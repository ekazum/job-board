"""Schema behaviour (sql/schema.sql): WAL mode, de-duplication, the outcome/status rule, enum coverage."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from job_board.enums.outcome import Outcome
from job_board.enums.platform import Platform
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.storage.database import LATEST_VERSION, Database

from tests.http_fakes import FIXTURES

INSERT_POSTING = (
    "INSERT INTO postings (source, external_id, company, title, url, status, outcome) "
    "VALUES (:source, :external_id, :company, :title, :url, :status, :outcome) "
    "ON CONFLICT (source, external_id) DO NOTHING"
)
POSTING: dict[str, str | None] = {
    "source": "manual",
    "external_id": "https://example.com/jobs/1",
    "company": "Example",
    "title": "Backend Engineer",
    "url": "https://example.com/jobs/1",
    "status": "new",
    "outcome": None,
}
INSERT_COMPANY = "INSERT INTO companies (name, platform) VALUES (:name, :platform)"


def _insert_posting(connection: sqlite3.Connection, **overrides: str | None) -> int:
    """Insert a posting, skipping duplicates the way the app does; returns the number of rows inserted."""
    return connection.execute(INSERT_POSTING, {**POSTING, **overrides}).rowcount


def test_insert_or_ignore_would_hide_check_violations(database: Database) -> None:
    """Guards the choice of ON CONFLICT DO NOTHING: OR IGNORE drops an invalid row without an error."""
    with closing(database.connect()) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO postings (source, external_id, company, title, url, status) "
            "VALUES ('manual', 'x', 'Example', 'Engineer', 'x', 'archived')"
        )
        assert cursor.rowcount == 0


def test_initialize_creates_folder_and_uses_wal(database: Database) -> None:
    assert database.path.is_file()
    with closing(database.connect()) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_initialize_is_idempotent(database: Database) -> None:
    database.initialize()
    with closing(database.connect()) as connection:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"companies", "postings"} <= tables


def test_new_posting_gets_defaults(database: Database) -> None:
    with closing(database.connect()) as connection:
        connection.execute(
            "INSERT INTO postings (source, external_id, company, title, url) "
            "VALUES ('manual', 'x', 'Example', 'Engineer', 'x')"
        )
        row = connection.execute("SELECT status, outcome, text, note, created_at FROM postings WHERE external_id = 'x'").fetchone()
    assert (row["status"], row["outcome"], row["text"], row["note"]) == ("new", None, "", "")
    assert row["created_at"].endswith("Z")


def test_duplicate_source_and_external_id_is_ignored(database: Database) -> None:
    with closing(database.connect()) as connection:
        assert _insert_posting(connection) == 1
        connection.execute("UPDATE postings SET status = 'applied' WHERE external_id = :external_id", POSTING)
        assert _insert_posting(connection, title="Changed title") == 0
        row = connection.execute("SELECT COUNT(*) AS n, MAX(status) AS status, MAX(title) AS title FROM postings").fetchone()
    assert (row["n"], row["status"], row["title"]) == (1, "applied", "Backend Engineer")


def test_same_external_id_from_another_source_is_a_new_row(database: Database) -> None:
    with closing(database.connect()) as connection:
        _insert_posting(connection)
        assert _insert_posting(connection, source="greenhouse") == 1


def test_outcome_rejected_unless_closed(database: Database) -> None:
    with closing(database.connect()) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_posting(connection, status="applied", outcome="rejected")


def test_reopening_a_closed_posting_requires_clearing_outcome(database: Database) -> None:
    with closing(database.connect()) as connection:
        _insert_posting(connection, status="closed", outcome="rejected")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE postings SET status = 'applied' WHERE external_id = :external_id", POSTING)
        connection.execute("UPDATE postings SET status = 'applied', outcome = NULL WHERE external_id = :external_id", POSTING)


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "archived"), ("outcome", "ghosted"), ("source", "linkedin")],
)
def test_unknown_enum_values_rejected(database: Database, column: str, value: str) -> None:
    overrides = {column: value, "status": "closed"} if column == "outcome" else {column: value}
    with closing(database.connect()) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_posting(connection, **overrides)


# --- schema.sql lists enum values literally; these keep it in step with job_board/enums -------------------


@pytest.mark.parametrize("status", list(Status))
def test_schema_accepts_every_status(database: Database, status: Status) -> None:
    outcome = Outcome.OFFER if status is Status.CLOSED else None
    with closing(database.connect()) as connection:
        assert _insert_posting(connection, status=status, outcome=outcome) == 1


@pytest.mark.parametrize("outcome", list(Outcome))
def test_schema_accepts_every_outcome_on_a_closed_posting(database: Database, outcome: Outcome) -> None:
    with closing(database.connect()) as connection:
        assert _insert_posting(connection, status=Status.CLOSED, outcome=outcome) == 1


@pytest.mark.parametrize("source", list(Source))
def test_schema_accepts_every_source(database: Database, source: Source) -> None:
    with closing(database.connect()) as connection:
        assert _insert_posting(connection, source=source) == 1


@pytest.mark.parametrize("platform", list(Platform))
def test_schema_accepts_every_platform(database: Database, platform: Platform) -> None:
    with closing(database.connect()) as connection:
        connection.execute(INSERT_COMPANY, {"name": "Acme", "platform": platform})


# --- versions and migrations ------------------------------------------------------------------------------


def _version(database: Database) -> int:
    with closing(database.connect()) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def test_new_database_is_created_at_the_latest_version(database: Database) -> None:
    assert _version(database) == LATEST_VERSION
    with closing(database.connect()) as connection:
        columns = {row["name"] for row in connection.execute("SELECT name FROM pragma_table_info('companies')")}
    assert {"company_uid", "token", "tenant", "wd_host", "site", "last_error"} <= columns


def test_version_1_file_is_migrated_and_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    shutil.copyfile(FIXTURES / "job_board_v1.db", path)  # created with the schema as committed before versioning
    database = Database(path)
    database.initialize()
    assert _version(database) == LATEST_VERSION
    with closing(database.connect()) as connection:
        company = connection.execute("SELECT name, platform, slug, verified, enabled, last_error FROM companies").fetchone()
        posting = connection.execute("SELECT status, outcome, title FROM postings").fetchone()
        connection.execute(INSERT_COMPANY, {"name": "Nvidia", "platform": Platform.WORKDAY})  # allowed only after v2
        connection.execute(INSERT_COMPANY, {"name": "Google", "platform": Platform.GOOGLE})  # allowed only after v5
        assert _insert_posting(connection, source=Source.AMAZON) == 1
    assert tuple(company) == ("Acme", "greenhouse", "acme", 1, 0, None)
    assert tuple(posting) == ("closed", "offer", "Backend Engineer")
    database.initialize()  # nothing left to migrate
    assert _version(database) == LATEST_VERSION


def test_file_from_newer_code_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(f"PRAGMA user_version = {LATEST_VERSION + 1}")
    with pytest.raises(RuntimeError, match="schema version"):
        Database(path).initialize()


# --- companies --------------------------------------------------------------------------------------------


def test_company_name_is_unique_case_insensitive(database: Database) -> None:
    with closing(database.connect()) as connection:
        connection.execute(INSERT_COMPANY, {"name": "Acme", "platform": None})
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(INSERT_COMPANY, {"name": "acme", "platform": None})


def test_company_platform_starts_null_and_rejects_unknown(database: Database) -> None:
    with closing(database.connect()) as connection:
        connection.execute("INSERT INTO companies (name) VALUES ('Acme')")
        row = connection.execute("SELECT platform, verified, enabled FROM companies WHERE name = 'Acme'").fetchone()
        assert (row["platform"], row["verified"], row["enabled"]) == (None, 0, 1)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE companies SET platform = 'taleo' WHERE name = 'Acme'")


def test_fit_must_be_between_0_and_10(database: Database) -> None:
    with closing(database.connect()) as connection:
        _insert_posting(connection)
        connection.execute("UPDATE postings SET fit = 10 WHERE external_id = :external_id", POSTING)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE postings SET fit = 11 WHERE external_id = :external_id", POSTING)


def test_v1_file_reaches_the_latest_version_with_a_blank_profile(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    shutil.copyfile(FIXTURES / "job_board_v1.db", path)
    Database(path).initialize()
    with closing(sqlite3.connect(path)) as connection:
        columns = {row[1] for row in connection.execute("SELECT * FROM pragma_table_info('postings')")}
        profile = connection.execute("SELECT cv_text, location, allow_fully_remote, include_keywords FROM profile").fetchall()
    assert {"fit", "location", "fit_reason", "fit_gaps", "is_remote", "country"} <= columns
    assert profile == [("", "", 0, "[]")]  # created by migration 6: no location, so nothing passes until one is set


def test_profile_table_holds_one_row_created_with_the_schema(database: Database) -> None:
    with closing(database.connect()) as connection:
        assert [tuple(row) for row in connection.execute("SELECT id, location, allow_fully_remote FROM profile")] == [(1, "", 0)]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO profile (id, cv_text) VALUES (2, 'second')")
