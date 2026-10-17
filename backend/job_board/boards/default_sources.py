"""The standard set of board sources, shared by discover and scan."""

from collections.abc import Sequence

from job_board.boards.ashby_source import AshbySource
from job_board.boards.board_source import BoardSource
from job_board.boards.comeet_source import ComeetSource
from job_board.boards.greenhouse_source import GreenhouseSource
from job_board.boards.lever_source import LeverSource
from job_board.boards.workday_source import WorkdaySource
from job_board.enums.platform import Platform
from job_board.http_client import HttpClient
from job_board.keyword_filter import KeywordFilter


def default_sources(
    http: HttpClient,
    role_filter: KeywordFilter | None = None,
    locations: Sequence[str] = (),
) -> dict[Platform, BoardSource]:
    """One source per supported platform, all sharing one HTTP client. role_filter and locations only affect
    Workday, whose sites are searched (and their job details fetched) per wanted role rather than listed in full."""
    sources: list[BoardSource] = [
        GreenhouseSource(http),
        LeverSource(http),
        AshbySource(http),
        ComeetSource(http),
        WorkdaySource(http, role_filter, locations),
    ]
    return {source.platform: source for source in sources}
