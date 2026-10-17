"""The standard set of board sources, shared by discover and scan."""

from job_board.boards.ashby_source import AshbySource
from job_board.boards.board_source import BoardSource
from job_board.boards.comeet_source import ComeetSource
from job_board.boards.greenhouse_source import GreenhouseSource
from job_board.boards.lever_source import LeverSource
from job_board.enums.platform import Platform
from job_board.http_client import HttpClient


def default_sources(http: HttpClient) -> dict[Platform, BoardSource]:
    """One source per supported platform, all sharing one HTTP client."""
    sources: list[BoardSource] = [GreenhouseSource(http), LeverSource(http), AshbySource(http), ComeetSource(http)]
    return {source.platform: source for source in sources}
