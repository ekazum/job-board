"""Value object for one company to scan."""

from dataclasses import dataclass

from job_board.boards.board_ref import BoardRef


@dataclass(frozen=True)
class ScanTarget:
    """A verified, enabled company and the board to read."""

    company: str
    board: BoardRef
