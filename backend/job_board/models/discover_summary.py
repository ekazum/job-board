"""Result of a discover run."""

from job_board.models.run_summary import RunSummary


class DiscoverSummary(RunSummary):
    """A run's counts, plus added: the companies of pasted postings that this run put on the list."""

    added: int
