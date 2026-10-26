"""The standard set of board sources, shared by discover and scan."""

from collections.abc import Sequence

from job_board.boards.amazon_source import AmazonSource
from job_board.boards.apple_source import AppleSource
from job_board.boards.ashby_source import AshbySource
from job_board.boards.board_source import BoardSource
from job_board.boards.comeet_source import ComeetSource
from job_board.boards.eightfold_source import EightfoldSource
from job_board.boards.google_source import GoogleSource
from job_board.boards.greenhouse_source import GreenhouseSource
from job_board.boards.hibob_source import HibobSource
from job_board.boards.lever_source import LeverSource
from job_board.boards.meta_source import MetaSource
from job_board.boards.microsoft_source import MicrosoftSource
from job_board.boards.tyco_source import TycoSource
from job_board.boards.workday_source import WorkdaySource
from job_board.enums.platform import Platform
from job_board.rules.keyword_filter import KeywordFilter
from job_board.utils.http_client import HttpClient


def default_sources(
    http: HttpClient,
    role_filter: KeywordFilter | None = None,
    locations: Sequence[str] = (),
) -> dict[Platform, BoardSource]:
    """One source per supported platform, all sharing one HTTP client. role_filter and locations only affect the
    sites that are searched per wanted role rather than listed in full: Workday, Eightfold and the single-company
    careers sites (Google, Microsoft, Apple, Amazon, Meta)."""
    sources: list[BoardSource] = [
        GreenhouseSource(http),
        LeverSource(http),
        AshbySource(http),
        ComeetSource(http),
        HibobSource(http),
        TycoSource(http),
        WorkdaySource(http, role_filter, locations),
        EightfoldSource(http, role_filter, locations),
        GoogleSource(http, role_filter, locations),
        MicrosoftSource(http, role_filter, locations),
        AppleSource(http, role_filter, locations),
        AmazonSource(http, role_filter, locations),
        MetaSource(http, role_filter, locations),
    ]
    return {source.platform: source for source in sources}
