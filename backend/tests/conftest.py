"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from job_board.database import Database


@pytest.fixture
def anyio_backend() -> str:
    """Async tests (@pytest.mark.anyio) run on asyncio, like the app."""
    return "asyncio"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    """An initialized database in a not-yet-existing subfolder of a temp dir."""
    db = Database(tmp_path / "data" / "job_board.db")
    db.initialize()
    return db
