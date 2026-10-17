"""Score postings again: all of them in the background, or one on request."""

import asyncio
import logging
from collections.abc import Callable

from job_board.enums.status import Status
from job_board.location_sweep import LocationSweep
from job_board.models.location_sweep_result import LocationSweepResult
from job_board.models.posting import Posting
from job_board.models.rescore_status import RescoreStatus
from job_board.posting_repository import PostingRepository
from job_board.scorer import Scorer
from job_board.triage import Triage

logger = logging.getLogger(__name__)


class RescoreJob:
    """Re-score all: first the location rule on the stored postings (LocationSweep: postings in New outside the
    profile's location go to the Archive without an LLM call, ones it archived that now pass come back to New), then
    every posting not scored yet or still in New is scored, as one background task (one at a time) whose progress
    status() reports. rescore_one() does both for a single posting right away; apply_locations() only the first.

    A posting that had never been scored is triaged like a scanned one (fit below llm.threshold closes it as
    not_relevant); a posting scored before only gets its new fit, reason and gaps, so one you re-opened from the
    Archive after a low score stays where you put it.
    """

    def __init__(
        self,
        postings: PostingRepository,
        scorer_factory: Callable[[], Scorer],
        threshold_loader: Callable[[], int],
        locations: LocationSweep,
    ) -> None:
        self._postings = postings
        self._scorer_factory = scorer_factory
        self._threshold_loader = threshold_loader
        self._locations = locations
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

    def apply_locations(self) -> LocationSweepResult | None:
        """Apply the location rule to the stored postings; None while a Re-score all is running."""
        return None if self.running else self._locations.run()

    def start(self) -> bool:
        """Apply the location rule, then begin scoring in the background; False when a run is already going."""
        if self.running:
            return False
        swept = self._locations.run()
        logger.info("location rule: %d postings to the Archive, %d back to New", swept.archived, swept.restored)
        targets = self._postings.rescore_targets()
        self._done, self._total, self._error = 0, len(targets), None
        self._task = asyncio.create_task(self._rescore_all(targets))
        self._task.add_done_callback(self._finished)
        return True

    async def rescore_one(self, posting_id: int) -> Posting | None:
        """Apply the location rule to one posting and score it unless that archived it; None when it does not exist."""
        posting = self._postings.get(posting_id)
        if posting is None:
            return None
        posting = self._locations.apply(posting)
        if LocationSweep.archived_by_location(posting):
            return posting
        scorer = self._scorer_factory()
        try:
            return await self._rescore(scorer, Triage(self._threshold_loader()), posting)
        finally:
            await scorer.aclose()

    async def _rescore_all(self, targets: list[Posting]) -> None:
        """Score every target; the LLM client caps how many requests run at once."""
        scorer = self._scorer_factory()
        triage = Triage(self._threshold_loader())
        try:
            await asyncio.gather(*(self._rescore_counted(scorer, triage, posting) for posting in targets))
        finally:
            await scorer.aclose()
        logger.info("re-scored %d postings", self._done)

    async def _rescore_counted(self, scorer: Scorer, triage: Triage, posting: Posting) -> None:
        """Score one posting of a Re-score all and count it."""
        await self._rescore(scorer, triage, posting)
        self._done += 1

    async def _rescore(self, scorer: Scorer, triage: Triage, posting: Posting) -> Posting | None:
        """Score and store one posting; only a never-scored posting still in New is triaged."""
        fit = await scorer.score(title=posting.title, company=posting.company, location=posting.location, text=posting.text)
        if posting.fit is None and posting.status is Status.NEW:
            status, outcome = triage.decide(fit.fit)
        else:
            status, outcome = posting.status, posting.outcome
        return self._postings.save_fit(posting.id, fit, status, outcome)

    def _finished(self, task: asyncio.Task[None]) -> None:
        """Keep the reason a Re-score all stopped early, for status()."""
        if task.cancelled():
            self._error = "cancelled"
        elif task.exception() is not None:
            self._error = f"{type(task.exception()).__name__}: {task.exception()}"
            logger.error("re-score stopped: %s", self._error)
