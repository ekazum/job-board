"""Data access for the postings table; the statements live in sql/postings/."""

import sqlite3

from job_board.database import Database
from job_board.enums.source import Source
from job_board.models.posting import Posting
from job_board.utils.sql_files import sql


class PostingRepository:
    """Reads and writes rows of the postings table."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_all(self) -> list[Posting]:
        """All postings, newest first."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("postings/list_all.sql")).fetchall()
        return [self._to_posting(row) for row in rows]

    def get(self, posting_id: int) -> Posting | None:
        """One posting by id, or None when it does not exist."""
        with self._database.transaction() as connection:
            row = connection.execute(sql("postings/get_by_id.sql"), {"id": posting_id}).fetchone()
        return None if row is None else self._to_posting(row)

    def insert(
        self,
        *,
        source: Source,
        external_id: str,
        company: str,
        title: str,
        url: str,
        text: str,
    ) -> tuple[Posting, bool]:
        """Insert a posting as status new unless (source, external_id) already exists.

        Returns the stored row and whether it was created. An existing row is returned untouched, so a
        repeat never changes its status.
        """
        key = {"source": source, "external_id": external_id}
        with self._database.transaction() as connection:
            cursor = connection.execute(
                sql("postings/insert.sql"), {**key, "company": company, "title": title, "url": url, "text": text}
            )
            row = connection.execute(sql("postings/get_by_key.sql"), key).fetchone()
        return self._to_posting(row), cursor.rowcount == 1

    def save(self, posting: Posting) -> Posting | None:
        """Persist status, outcome and note of an existing posting; None when the row has disappeared."""
        values = {"id": posting.id, "status": posting.status, "outcome": posting.outcome, "note": posting.note}
        with self._database.transaction() as connection:
            cursor = connection.execute(sql("postings/save.sql"), values)
        return posting if cursor.rowcount == 1 else None

    @staticmethod
    def _to_posting(row: sqlite3.Row) -> Posting:
        """Convert a postings row into the API model."""
        return Posting.model_validate(dict(row))
