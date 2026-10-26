"""Microsoft careers (apply.careers.microsoft.com), an Eightfold site."""

from job_board.boards.board_ref import BoardRef
from job_board.boards.eightfold_source import EightfoldSource
from job_board.enums.platform import Platform
from job_board.enums.source import Source

API_ROOT = "https://apply.careers.microsoft.com/api/pcsx"
JOB_URL = "https://apply.careers.microsoft.com/careers/job/{}"
DOMAIN = "microsoft.com"


class MicrosoftSource(EightfoldSource):
    """Searches Microsoft's careers site once per wanted role and configured location, through the Eightfold API at
    a fixed address (domain microsoft.com) whatever the board. The board's slug is "microsoft"."""

    @property
    def platform(self) -> Platform:
        """Microsoft."""
        return Platform.MICROSOFT

    @property
    def source(self) -> Source:
        """Microsoft."""
        return Source.MICROSOFT

    def _api(self, board: BoardRef) -> tuple[str, str]:
        """Microsoft's API root and domain."""
        del board  # one site, whatever the slug
        return API_ROOT, DOMAIN

    def _job_url(self, board: BoardRef, position_id: str) -> str:
        """A position's page on Microsoft's site."""
        del board
        return JOB_URL.format(position_id)
