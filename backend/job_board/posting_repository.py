"""Data access for the postings table; the statements live in sql/postings/."""

import json
import sqlite3

from job_board.database import Database
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.models.posting import Posting
from job_board.models.posting_facets import PostingFacets
from job_board.posting_filter import PostingFilter
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

    def search(self, posting_filter: PostingFilter) -> list[Posting]:
        """Postings matching the filter bar (sql/postings/search.sql), newest first."""
        values = {
            "pattern": self._like_pattern(posting_filter.text),
            "in_text": int(posting_filter.in_text),
            "companies": json.dumps(list(posting_filter.companies)) if posting_filter.companies else None,
            "sources": json.dumps([str(source) for source in posting_filter.sources]) if posting_filter.sources else None,
            "min_fit": posting_filter.min_fit,
        }
        with self._database.transaction() as connection:
            rows = connection.execute(sql("postings/search.sql"), values).fetchall()
        return [self._to_posting(row) for row in rows]

    def facets(self) -> PostingFacets:
        """Companies and sources that have postings, and the unfiltered count of every status column."""
        with self._database.transaction() as connection:
            companies = [row["company"] for row in connection.execute(sql("postings/distinct_companies.sql"))]
            sources = [Source(row["source"]) for row in connection.execute(sql("postings/distinct_sources.sql"))]
            counts = {row["status"]: row["total"] for row in connection.execute(sql("postings/count_by_status.sql"))}
        totals = {status: int(counts.get(status, 0)) for status in Status}
        return PostingFacets(companies=companies, sources=sources, totals=totals)

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
    def _like_pattern(text: str) -> str | None:
        r"""'%text%' for LIKE ... ESCAPE '\', with the user's \, % and _ matched literally; None for blank text."""
        stripped = text.strip()
        if not stripped:
            return None
        escaped = stripped.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
        return f"%{escaped}%"

    @staticmethod
    def _to_posting(row: sqlite3.Row) -> Posting:
        """Convert a postings row into the API model."""
        return Posting.model_validate(dict(row))
