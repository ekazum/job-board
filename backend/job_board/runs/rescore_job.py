"""Score postings again: all of them in the background, or one on request."""

import asyncio
import logging
from collections.abc import Callable

from job_board.llm.scorer import Scorer
from job_board.models.posting import Posting
from job_board.models.rescore_status import RescoreStatus
from job_board.models.sweep_result import SweepResult
from job_board.rules.profile_sweep import ProfileSweep
from job_board.storage.posting_repository import PostingRepository

logger = logging.getLogger(__name__)


class RescoreJob:
    """Re-score all: first the profile's job-title keywords and location on the stored postings (ProfileSweep:
    postings in New that fail them go to the Archive without an LLM call, ones it archived that now pass come back to
    New), then every posting not scored yet or still in New is scored, as one background task (one at a time) whose
    progress status() reports. rescore_one() does both for a single posting right away; apply_filters() only the
    first.

    Scoring only stores the fit, reason and gaps: a posting stays in the column it is in, whatever its score.
    """

    def __init__(
        self,
        postings: PostingRepository,
        scorer_factory: Callable[[], Scorer],
        sweep: ProfileSweep,
    ) -> None:
        self._postings = postings
        self._scorer_factory = scorer_factory
        self._sweep = sweep
        self._task: asyncio.Task[None] | None = None
        self._done = 0
        self._total = 0
        self._error: str | None = None

    @property
    def running(self) -> bool:
        """Whether a Re-score all is in progress."""
        return self._task is not None and not self._task.done()

    def status(self) -> RescoreStatus:
        """Progress of the current or last Re-score all."""
        return RescoreStatus(running=self.running, done=self._done, total=self._total, error=self._error)

    def apply_filters(self) -> SweepResult | None:
        """Apply the keywords and the location to the stored postings; None while a Re-score all is running."""
        return None if self.running else self._sweep.run()

    def start(self) -> bool:
        """Apply the keywords and the location, then begin scoring in the background; False when a run is already
        going."""
        if self.running:
            return False
        swept = self._sweep.run()
        logger.info("keywords and location: %d postings to the Archive, %d back to New", swept.archived, swept.restored)
        targets = self._postings.rescore_targets()
        self._done, self._total, self._error = 0, len(targets), None
        task = asyncio.create_task(self._rescore_all(targets))
        task.add_done_callback(self._finished)
        self._task = task
        return True

    async def rescore_one(self, posting_id: int) -> Posting | None:
        """Apply the keywords and the location to one posting and score it unless that archived it; None when it does
        not exist."""
        posting = self._postings.get(posting_id)
        if posting is None:
            return None
        posting = self._sweep.apply(posting)
        if ProfileSweep.archived_by_rules(posting):
            return posting
        scorer = self._scorer_factory()
        try:
            return await self._rescore(scorer, posting)
        finally:
            await scorer.aclose()

    async def _rescore_all(self, targets: list[Posting]) -> None:
        """Score every target; the LLM client caps how many requests run at once."""
        scorer = self._scorer_factory()
        try:
            await asyncio.gather(*(self._rescore_counted(scorer, posting) for posting in targets))
        finally:
            await scorer.aclose()
        logger.info("re-scored %d postings", self._done)

    async def _rescore_counted(self, scorer: Scorer, posting: Posting) -> None:
        """Score one posting of a Re-score all and count it."""
        await self._rescore(scorer, posting)
        self._done += 1

    async def _rescore(self, scorer: Scorer, posting: Posting) -> Posting | None:
        """Score and store one posting, leaving its status and outcome as they are."""
        fit = await scorer.score(title=posting.title, company=posting.company, text=posting.text)
        return self._postings.save_fit(posting.id, fit, posting.status, posting.outcome)

    def _finished(self, task: asyncio.Task[None]) -> None:
        """Keep the reason a Re-score all stopped early, for status()."""
        if task.cancelled():
            self._error = "cancelled"
        elif task.exception() is not None:
            self._error = f"{type(task.exception()).__name__}: {task.exception()}"
            logger.error("re-score stopped: %s", self._error)
