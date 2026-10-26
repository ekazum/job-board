"""Apply the profile's job-title keywords and location to the stored postings."""

from collections.abc import Callable

from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.llm.fit_result import FitResult
from job_board.models.posting import Posting
from job_board.models.profile import Profile
from job_board.models.sweep_result import SweepResult
from job_board.rules.keyword_filter import KeywordFilter
from job_board.rules.location_resolver import LocationResolver
from job_board.rules.location_rule import LocationRule
from job_board.storage.posting_repository import PostingRepository


class ProfileSweep:
    """Applies the role filter (KeywordFilter) and the location rule (LocationRule) to every posting in New and every
    posting they archived before: one in New that fails either moves to the Archive (closed as not_relevant, fit
    cleared, fit_reason "keywords: ..." or "location: ..."); an archived one that now passes both goes back to New,
    unscored. Postings you pasted, postings you moved yourself (Applied, Interview, Closed with another outcome) and
    the scorer's own rejects are left alone. On the way every posting's is_remote is refreshed and a posting without a
    country gets the one its location resolves to.
    """

    def __init__(self, postings: PostingRepository, profile_loader: Callable[[], Profile | None]) -> None:
        self._postings = postings
        self._profile_loader = profile_loader

    def run(self) -> SweepResult:
        """Apply the rules as the profile now stands to all stored postings."""
        keywords, location = self._rules()
        postings = [self._with_facts(posting) for posting in self._postings.list_all()]
        decided = [(posting, decision) for posting in postings if (decision := self._decide(keywords, location, posting)) is not None]
        self._postings.set_location_facts((posting.id, posting.is_remote, posting.country) for posting in postings)
        self._postings.save_fits((posting.id, *decision) for posting, decision in decided)
        moves = [(posting.status, status) for posting, (_, status, _) in decided]
        return SweepResult(
            archived=moves.count((Status.NEW, Status.CLOSED)),
            restored=moves.count((Status.CLOSED, Status.NEW)),
        )

    def apply(self, posting: Posting) -> Posting:
        """Apply the rules to one posting; returns it as stored afterwards."""
        posting = self._with_facts(posting)
        decision = self._decide(*self._rules(), posting)
        self._postings.set_location_facts([(posting.id, posting.is_remote, posting.country)])
        if decision is not None:
            self._postings.save_fit(posting.id, *decision)
        return self._postings.get(posting.id) or posting

    @staticmethod
    def archived_by_rules(posting: Posting) -> bool:
        """The role filter or the location rule put this posting in the Archive."""
        reason = posting.fit_reason
        rejected = KeywordFilter.is_rejection(reason) or LocationRule.is_rejection(reason)
        return posting.status is Status.CLOSED and posting.outcome is Outcome.NOT_RELEVANT and rejected

    def _rules(self) -> tuple[KeywordFilter, LocationRule]:
        """The role filter and the location rule of the profile as currently stored."""
        profile = self._profile_loader()
        return KeywordFilter.for_profile(profile), LocationRule.for_profile(profile)

    @classmethod
    def _decide(cls, keywords: KeywordFilter, location: LocationRule, posting: Posting) -> tuple[FitResult, Status, Outcome | None] | None:
        """The fit, status and outcome the rules give this posting, or None when it stays as it is."""
        archived = cls.archived_by_rules(posting)
        if posting.source is Source.MANUAL or (posting.status is not Status.NEW and not archived):
            return None
        reason = keywords.rejection(posting.title) or location.rejection(
            country=posting.country, location=posting.location, title=posting.title, text=posting.text
        )
        if reason is not None:
            return None if archived and reason == posting.fit_reason else (FitResult(None, reason), Status.CLOSED, Outcome.NOT_RELEVANT)
        return (FitResult(None, None), Status.NEW, None) if archived else None

    @staticmethod
    def _with_facts(posting: Posting) -> Posting:
        """The posting with is_remote as LocationRule says, and a country resolved from its location if it had none."""
        is_remote = LocationRule.is_remote(location=posting.location, title=posting.title, text=posting.text)
        country = posting.country or LocationResolver.shared().resolve(posting.location)
        return posting.model_copy(update={"is_remote": is_remote, "country": country})
