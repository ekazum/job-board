"""Data access for the companies table; the statements live in sql/companies/."""

import sqlite3

from job_board.boards.board_ref import BoardRef
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.boards.scan_target import ScanTarget
from job_board.config.company_seed import CompanySeed
from job_board.enums.platform import Platform
from job_board.models.company import Company
from job_board.storage.database import Database
from job_board.utils.sql_files import sql


class CompanyRepository:
    """Reads and writes rows of the companies table."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_all(self) -> list[Company]:
        """All companies, alphabetically."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("companies/list_all.sql")).fetchall()
        return [self._to_company(row) for row in rows]

    def get(self, company_id: int) -> Company | None:
        """One company by id, or None when it does not exist."""
        with self._database.transaction() as connection:
            row = connection.execute(sql("companies/get_by_id.sql"), {"id": company_id}).fetchone()
        return None if row is None else self._to_company(row)

    def insert(self, name: str, domain: str | None = None, careers_url: str | None = None) -> tuple[Company, bool]:
        """Add a company unless one with the same name (any case) exists; an existing row is left untouched.

        Returns the stored row and whether it was created; discovery fills in the other columns later.
        """
        values = {"name": name, "domain": domain, "careers_url": careers_url}
        with self._database.transaction() as connection:
            cursor = connection.execute(sql("companies/insert.sql"), values)
            row = connection.execute(sql("companies/get_by_name.sql"), {"name": name}).fetchone()
        return self._to_company(row), cursor.rowcount == 1

    def set_enabled(self, company_id: int, enabled: bool) -> Company | None:
        """Turn scanning on or off for a company; None when it does not exist."""
        return self._update(sql("companies/set_enabled.sql"), {"id": company_id, "enabled": int(enabled)})

    def set_careers_url(self, company_id: int, careers_url: str | None) -> Company | None:
        """Set or clear the page Discover fetches first; None when the company does not exist."""
        return self._update(sql("companies/set_careers_url.sql"), {"id": company_id, "careers_url": careers_url})

    def record_discovery(self, seed: CompanySeed, finding: DiscoveryFinding) -> None:
        """Upsert a company by name (any case) with what discovery found and clear last_error; enabled is kept."""
        board = finding.board
        values = {
            "name": seed.name,
            "domain": seed.domain,
            "careers_url": finding.careers_url,
            "platform": Platform.NONE if board is None else board.platform,
            "slug": None if board is None else board.slug,
            "company_uid": None if board is None else board.company_uid,
            "token": None if board is None else board.token,
            "tenant": None if board is None else board.tenant,
            "wd_host": None if board is None else board.wd_host,
            "site": None if board is None else board.site,
            "verified": int(finding.verified),
        }
        with self._database.transaction() as connection:
            connection.execute(sql("companies/record_discovery.sql"), values)

    def record_failure(self, seed: CompanySeed, error: str) -> None:
        """Save a discovery error, keeping what an earlier run found (or adding the company if it is new)."""
        values = {"name": seed.name, "domain": seed.domain, "careers_url": seed.careers_url, "last_error": error}
        with self._database.transaction() as connection:
            connection.execute(sql("companies/record_failure.sql"), values)

    def set_last_error(self, name: str, error: str | None) -> None:
        """Save (or clear, with None) the latest scan error of a company."""
        with self._database.transaction() as connection:
            connection.execute(sql("companies/set_last_error.sql"), {"name": name, "last_error": error})

    def list_seeds(self) -> list[CompanySeed]:
        """Stored companies that have a domain, as discovery input, alphabetically."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("companies/list_seeds.sql")).fetchall()
        return [CompanySeed(name=row["name"], domain=row["domain"], careers_url=row["careers_url"]) for row in rows]

    def list_scannable(self) -> list[ScanTarget]:
        """Companies that are verified and enabled and have a board, alphabetically."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("companies/list_scannable.sql")).fetchall()
        return [ScanTarget(company=row["name"], board=self._to_board(row)) for row in rows]

    def _update(self, statement: str, values: dict[str, object]) -> Company | None:
        """Run an UPDATE by id and return the row afterwards; None when the company does not exist."""
        with self._database.transaction() as connection:
            connection.execute(statement, values)
            row = connection.execute(sql("companies/get_by_id.sql"), {"id": values["id"]}).fetchone()
        return None if row is None else self._to_company(row)

    @staticmethod
    def _to_board(row: sqlite3.Row) -> BoardRef:
        """The board columns of a companies row."""
        return BoardRef(
            platform=Platform(row["platform"]),
            slug=row["slug"],
            company_uid=row["company_uid"],
            token=row["token"],
            tenant=row["tenant"],
            wd_host=row["wd_host"],
            site=row["site"],
        )

    @staticmethod
    def _to_company(row: sqlite3.Row) -> Company:
        """Convert a companies row into the API model."""
        return Company.model_validate(dict(row))
