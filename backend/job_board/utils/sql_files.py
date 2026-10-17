"""Load SQL statements from the job_board/sql folder."""

from functools import cache
from importlib.resources import files

SQL_PACKAGE = "job_board"
SQL_FOLDER = "sql"


@cache
def sql(name: str) -> str:
    """The text of job_board/sql/<name>, e.g. sql("postings/list_all.sql"); read once, then cached."""
    return files(SQL_PACKAGE).joinpath(SQL_FOLDER, *name.split("/")).read_text(encoding="utf-8")
