"""SQLite connection factory and schema initialization."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from job_board.utils.sql_files import sql

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_SECONDS = 5.0


class Database:
    """Opens connections to the job-board SQLite file and creates its schema (sql/schema.sql) in WAL mode."""

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
        """Create the data folder and run sql/schema.sql (WAL mode, tables, index). Idempotent."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            connection.executescript(sql("schema.sql"))
        logger.info("Database ready at %s", self._path)
