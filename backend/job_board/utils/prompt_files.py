"""Load prompt texts from the job_board/prompts folder."""

from functools import cache
from importlib.resources import files

PROMPT_PACKAGE = "job_board"
PROMPT_FOLDER = "prompts"


@cache
def prompt(name: str) -> str:
    """The text of job_board/prompts/<name>, e.g. prompt("score_system.txt"); read once, then cached."""
    return files(PROMPT_PACKAGE).joinpath(PROMPT_FOLDER, name).read_text(encoding="utf-8").strip()
