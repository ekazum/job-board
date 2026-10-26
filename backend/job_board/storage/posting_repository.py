"""Data access for the postings table; the statements live in sql/postings/."""

import json
import sqlite3
from collections.abc import Iterable

from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.llm.fit_result import FitResult
from job_board.models.posting import Posting
from job_board.models.posting_facets import PostingFacets
from job_board.rules.place_names import PlaceNames
from job_board.storage.database import Database
from job_board.storage.posting_filter import PostingFilter
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
            "location": PlaceNames.normalize(posting_filter.location) or None,
            "archived": int(posting_filter.archived),
        }
        with self._database.transaction() as connection:
            connection.create_function("normalized_location", 1, PlaceNames.normalize, deterministic=True)
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
        location: str = "",
        is_remote: bool = False,
        country: str | None = None,
        status: Status = Status.NEW,
        outcome: Outcome | None = None,
        fit: FitResult | None = None,
    ) -> tuple[Posting, bool]:
        """Insert a posting unless (source, external_id) already exists.

        Returns the stored row and whether it was created. An existing row is returned untouched, so a
        repeat never changes its status or score.
        """
        key = {"source": source, "external_id": external_id}
        values = {
            **key,
            "company": company,
            "title": title,
            "url": url,
            "text": text,
            "location": location,
            "is_remote": int(is_remote),
            "country": country,
            "status": status,
            "outcome": outcome,
            **self._fit_columns(fit),
        }
        with self._database.transaction() as connection:
            cursor = connection.execute(sql("postings/insert.sql"), values)
            row = connection.execute(sql("postings/get_by_key.sql"), key).fetchone()
        return self._to_posting(row), cursor.rowcount == 1

    def exists(self, source: Source, external_id: str) -> bool:
        """Whether a posting with this dedup key is already stored."""
        with self._database.transaction() as connection:
            row = connection.execute(sql("postings/exists_by_key.sql"), {"source": source, "external_id": external_id}).fetchone()
        return bool(row["found"])

    def fill_locations(self, source: Source, locations: Iterable[tuple[str, str, bool, str | None]]) -> None:
        """Give stored postings of this source a location, is_remote and country, from (external_id, location,
        is_remote, country), where they have no location yet."""
        values = [
            {"source": source, "external_id": external_id, "location": location, "is_remote": int(is_remote), "country": country}
            for external_id, location, is_remote, country in locations
            if location
        ]
        if values:
            with self._database.transaction() as connection:
                connection.executemany(sql("postings/fill_location.sql"), values)

    def set_location_facts(self, facts: Iterable[tuple[int, bool, str | None]]) -> None:
        """Store is_remote, and the country where none is stored yet, from (id, is_remote, country)."""
        values = [{"id": posting_id, "is_remote": int(is_remote), "country": country} for posting_id, is_remote, country in facts]
        with self._database.transaction() as connection:
            connection.executemany(sql("postings/set_location_facts.sql"), values)

    def delete_rejects(self) -> int:
        """Delete the postings the role filter or the location rule archived; returns how many."""
        with self._database.transaction() as connection:
            return connection.execute(sql("postings/delete_rejects.sql")).rowcount

    def save_fit(self, posting_id: int, fit: FitResult, status: Status, outcome: Outcome | None) -> Posting | None:
        """Store a scoring result and the status/outcome it leads to; None when the posting no longer exists."""
        values = {"id": posting_id, "status": status, "outcome": outcome, **self._fit_columns(fit)}
        with self._database.transaction() as connection:
            connection.execute(sql("postings/save_fit.sql"), values)
            row = connection.execute(sql("postings/get_by_id.sql"), {"id": posting_id}).fetchone()
        return None if row is None else self._to_posting(row)

    def save_fits(self, results: Iterable[tuple[int, FitResult, Status, Outcome | None]]) -> None:
        """save_fit for many postings at once, from (id, fit, status, outcome)."""
        values = [
            {"id": posting_id, "status": status, "outcome": outcome, **self._fit_columns(fit)}
            for posting_id, fit, status, outcome in results
        ]
        with self._database.transaction() as connection:
            connection.executemany(sql("postings/save_fit.sql"), values)

    def rescore_targets(self) -> list[Posting]:
        """Postings Re-score all works on: not scored yet, or still in New, except those the location rule archived."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("postings/rescore_targets.sql")).fetchall()
        return [self._to_posting(row) for row in rows]

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
    def _fit_columns(fit: FitResult | None) -> dict[str, object]:
        """fit, fit_reason and fit_gaps (a JSON array) for the insert/update statements."""
        if fit is None:
            return {"fit": None, "fit_reason": None, "fit_gaps": None}
        return {"fit": fit.fit, "fit_reason": fit.reason, "fit_gaps": json.dumps(list(fit.gaps))}

    @staticmethod
    def _to_posting(row: sqlite3.Row) -> Posting:
        """Convert a postings row into the API model; fit_gaps is stored as JSON text, is_remote as 0/1."""
        data = dict(row)
        gaps = data.get("fit_gaps")
        data["fit_gaps"] = json.loads(gaps) if isinstance(gaps, str) else []
        data["is_remote"] = bool(data.get("is_remote"))
        return Posting.model_validate(data)
