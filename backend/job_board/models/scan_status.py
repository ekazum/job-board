"""Progress of the current or last scan."""

from job_board.models.scan_progress import ScanProgress


class ScanStatus(ScanProgress):
    """running is false before the first scan and after one ends; error says why one stopped early."""

    running: bool
    error: str | None = None
