"""Apply the profile's location rule to the stored postings."""

from collections.abc import Callable

from job_board.enums.outcome import Outcome
from job_board.enums.status import Status
from job_board.fit_result import FitResult
from job_board.location_resolver import LocationResolver
from job_board.location_rule import LocationRule
from job_board.models.location_sweep_result import LocationSweepResult
from job_board.models.posting import Posting
from job_board.posting_repository import PostingRepository


class LocationSweep:
    """Applies the location rule to every posting in New and every posting the rule archived before: one in New that
    fails moves to the Archive (closed as not_relevant, fit cleared, fit_reason "location: ..."); an archived one that
    now passes goes back to New, unscored. Postings you moved yourself (Applied, Interview, Closed with another
    outcome) and the scorer's own rejects are left alone. On the way every posting's is_remote is refreshed and a
    posting without a country gets the one its location resolves to.
    """

    def __init__(self, postings: PostingRepository, rule_loader: Callable[[], LocationRule]) -> None:
        self._postings = postings
        self._rule_loader = rule_loader

    def run(self) -> LocationSweepResult:
        """Apply the rule as the profile now stands to all stored postings."""
        rule = self._rule_loader()
        postings = [self._with_facts(posting) for posting in self._postings.list_all()]
        decided = [(posting, decision) for posting in postings if (decision := self._decide(rule, posting)) is not None]
        self._postings.set_location_facts((posting.id, posting.is_remote, posting.country) for posting in postings)
        self._postings.save_fits((posting.id, *decision) for posting, decision in decided)
        moves = [(posting.status, status) for posting, (_, status, _) in decided]
        return LocationSweepResult(
            archived=moves.count((Status.NEW, Status.CLOSED)),
            restored=moves.count((Status.CLOSED, Status.NEW)),
        )

    def apply(self, posting: Posting) -> Posting:
        """Apply the rule to one posting; returns it as stored afterwards."""
        posting = self._with_facts(posting)
        decision = self._decide(self._rule_loader(), posting)
        self._postings.set_location_facts([(posting.id, posting.is_remote, posting.country)])
        if decision is not None:
            self._postings.save_fit(posting.id, *decision)
        return self._postings.get(posting.id) or posting

    @staticmethod
    def archived_by_location(posting: Posting) -> bool:
        """The location rule put this posting in the Archive."""
        return posting.status is Status.CLOSED and posting.outcome is Outcome.NOT_RELEVANT and LocationRule.is_rejection(posting.fit_reason)

    @classmethod
    def _decide(cls, rule: LocationRule, posting: Posting) -> tuple[FitResult, Status, Outcome | None] | None:
        """The fit, status and outcome the rule gives this posting, or None when it stays as it is."""
        archived = cls.archived_by_location(posting)
        if posting.status is not Status.NEW and not archived:
            return None
        reason = rule.rejection(country=posting.country, location=posting.location, title=posting.title, text=posting.text)
        if reason is not None:
            return None if archived and reason == posting.fit_reason else (FitResult(None, reason), Status.CLOSED, Outcome.NOT_RELEVANT)
        return (FitResult(None, None), Status.NEW, None) if archived else None

    @staticmethod
    def _with_facts(posting: Posting) -> Posting:
        """The posting with is_remote as LocationRule says, and a country resolved from its location if it had none."""
        is_remote = LocationRule.is_remote(location=posting.location, title=posting.title, text=posting.text)
        country = posting.country or LocationResolver.shared().resolve(posting.location)
        return posting.model_copy(update={"is_remote": is_remote, "country": country})
