"""SQLite connection factory, schema creation and migrations."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from job_board.utils.sql_files import sql

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_SECONDS = 5.0
LATEST_VERSION = 6
# Files created before versioning carry user_version 0 but already hold the version-1 tables.
UNSTAMPED_EXISTING_VERSION = 1
MIGRATIONS: dict[int, str] = {
    2: "migrations/002_add_workday.sql",
    3: "migrations/003_add_fit.sql",
    4: "migrations/004_add_scoring.sql",
    5: "migrations/005_add_company_sites.sql",
    6: "migrations/006_add_profile_locations.sql",
}


class Database:
    """Opens connections to the job-board SQLite file; creates it from sql/schema.sql or migrates it forward."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Location of the SQLite file."""
        return self._path

    def connect(self) -> sqlite3.Connection:
        """Open a new connection with dict-like rows; the caller is responsible for closing it."""
        connection = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a transaction: committed on success, rolled back on error, always closed."""
        with closing(self.connect()) as connection, connection:
            yield connection

    def initialize(self) -> None:
        """Create the database at the latest schema version, or apply the migrations it is missing. Idempotent.

        Each migration file wraps itself in BEGIN/COMMIT; a failure leaves the file at its previous version.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            version = self._version(connection)
            if version > LATEST_VERSION:
                raise RuntimeError(f"{self._path} is schema version {version}; this code knows up to {LATEST_VERSION}")
            if version == 0:
                connection.executescript(sql("schema.sql"))
                logger.info("Created %s at schema version %d", self._path, LATEST_VERSION)
                return
            for target in range(version + 1, LATEST_VERSION + 1):
                connection.executescript(sql(MIGRATIONS[target]))
                logger.info("Migrated %s to schema version %d", self._path, target)

    @staticmethod
    def _version(connection: sqlite3.Connection) -> int:
        """The file's schema version; 0 for an empty file."""
        stamped = int(connection.execute(sql("meta/user_version.sql")).fetchone()[0])
        if stamped > 0:
            return stamped
        tables = {row["name"] for row in connection.execute(sql("meta/table_names.sql"))}
        return UNSTAMPED_EXISTING_VERSION if "companies" in tables else 0
