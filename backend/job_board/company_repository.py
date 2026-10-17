"""Data access for the companies table; the statements live in sql/companies/."""

import sqlite3

from job_board.boards.board_ref import BoardRef
from job_board.boards.discovery_finding import DiscoveryFinding
from job_board.boards.scan_target import ScanTarget
from job_board.company_seed import CompanySeed
from job_board.database import Database
from job_board.enums.platform import Platform
from job_board.models.company import Company
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

    def insert(self, name: str, domain: str | None = None) -> tuple[Company, bool]:
        """Add a company unless one with the same name (any case) exists; an existing row is left untouched.

        Returns the stored row and whether it was created; discovery fills in the other columns later.
        """
        with self._database.transaction() as connection:
            cursor = connection.execute(sql("companies/insert.sql"), {"name": name, "domain": domain})
            row = connection.execute(sql("companies/get_by_name.sql"), {"name": name}).fetchone()
        return self._to_company(row), cursor.rowcount == 1

    def set_enabled(self, company_id: int, enabled: bool) -> Company | None:
        """Turn scanning on or off for a company; None when it does not exist."""
        with self._database.transaction() as connection:
            connection.execute(sql("companies/set_enabled.sql"), {"id": company_id, "enabled": int(enabled)})
            row = connection.execute(sql("companies/get_by_id.sql"), {"id": company_id}).fetchone()
        return None if row is None else self._to_company(row)

    def record_discovery(self, seed: CompanySeed, finding: DiscoveryFinding) -> Company:
        """Upsert a company by name (any case) with what discovery found; enabled is left as it was."""
        values = {
            "name": seed.name,
            "domain": seed.domain,
            "careers_url": finding.careers_url,
            "platform": Platform.NONE if finding.board is None else finding.board.platform,
            "slug": None if finding.board is None else finding.board.slug,
            "verified": int(finding.verified),
        }
        with self._database.transaction() as connection:
            connection.execute(sql("companies/record_discovery.sql"), values)
            row = connection.execute(sql("companies/get_by_name.sql"), {"name": seed.name}).fetchone()
        return self._to_company(row)

    def list_seeds(self) -> list[CompanySeed]:
        """Stored companies that have a domain, as discovery input, alphabetically."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("companies/list_seeds.sql")).fetchall()
        return [CompanySeed(name=row["name"], domain=row["domain"], careers_url=row["careers_url"]) for row in rows]

    def list_scannable(self) -> list[ScanTarget]:
        """Companies that are verified and enabled and have a board, alphabetically."""
        with self._database.transaction() as connection:
            rows = connection.execute(sql("companies/list_scannable.sql")).fetchall()
        return [
            ScanTarget(company=row["name"], board=BoardRef(platform=Platform(row["platform"]), slug=row["slug"]))
            for row in rows
        ]

    @staticmethod
    def _to_company(row: sqlite3.Row) -> Company:
        """Convert a companies row into the API model."""
        return Company.model_validate(dict(row))
