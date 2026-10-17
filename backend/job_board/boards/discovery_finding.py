"""Value object for what discovery learned about one company."""

from dataclasses import dataclass

from job_board.boards.board_ref import BoardRef


@dataclass(frozen=True)
class DiscoveryFinding:
    """board is None when no supported platform was found (stored as platform=none).
    verified is True only when the board's public API answered 200 with a jobs array.
    careers_url is the page the board link was found on, if any."""

    board: BoardRef | None
    verified: bool
    careers_url: str | None
