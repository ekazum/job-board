"""Score postings against the candidate profile with the configured LLM."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from pydantic import ValidationError

from job_board.config.llm_settings import LlmSettings
from job_board.llm.fit_result import FitResult
from job_board.llm.llm_client import LlmClient
from job_board.llm.llm_error import LlmError
from job_board.models.fit_assessment import FitAssessment
from job_board.storage.profile_repository import ProfileRepository
from job_board.utils.prompt_files import prompt

logger = logging.getLogger(__name__)

ATTEMPTS = 2  # a malformed answer is retried once
NO_PROFILE = "no profile"
PARSE_ERROR = "parse error"


class Scorer:
    """Asks the LLM how well one posting fits the profile (prompts/score_system.txt holds the rubric and the JSON
    schema; prompts/score_user.txt the CV, targets and posting, the description cut to max_text_chars).

    The answer is validated with FitAssessment; an invalid one is asked again once, then the fit is None with reason
    "parse error". Without a profile the LLM is not called (reason "no profile"); an LLM failure gives reason
    "llm error: ...". An answer marked "relevant": false scores 0.
    The LLM client's own limits apply: concurrency per provider, one retry on 429/5xx honouring Retry-After.
    """

    def __init__(
        self,
        llm: LlmClient | None,
        profiles: ProfileRepository,
        max_text_chars: int,
        setup_error: str | None = None,
    ) -> None:
        self._llm = llm
        self._profiles = profiles
        self._max_text_chars = max_text_chars
        self._setup_error = setup_error

    @classmethod
    def from_settings(cls, settings: LlmSettings, profiles: ProfileRepository, environ: Mapping[str, str]) -> Scorer:
        """A scorer on the configured provider; when it cannot be set up (e.g. an API key is missing) every posting
        gets fit None and the reason."""
        try:
            llm = LlmClient.from_settings(settings, environ)
        except ValueError as error:
            return cls(None, profiles, settings.max_text_chars, setup_error=str(error))
        return cls(llm, profiles, settings.max_text_chars)

    async def score(self, *, title: str, company: str, location: str, text: str) -> FitResult:
        """How well this posting fits the stored profile."""
        profile = self._profiles.get()
        if profile is None or not profile.cv_text.strip():
            return FitResult(None, NO_PROFILE)
        if self._llm is None:
            return FitResult(None, f"llm error: {self._setup_error}")
        prompt_text = prompt("score_user.txt").format(
            cv_text=profile.cv_text.strip(),
            targets=profile.targets.strip() or "(none given)",
            title=title,
            company=company,
            location=location or "(not given)",
            text=text[: self._max_text_chars],
        )
        for attempt in range(1, ATTEMPTS + 1):
            try:
                raw = await self._llm.score(prompt_text)
            except LlmError as error:
                return FitResult(None, f"llm error: {error}")
            try:
                assessment = FitAssessment.model_validate_json(raw)
            except ValidationError:
                logger.info("%s / %s: unusable answer (attempt %d): %.200s", company, title, attempt, raw)
                continue
            fit = assessment.fit if assessment.relevant else 0
            return FitResult(fit, assessment.reason.strip(), tuple(gap.strip() for gap in assessment.gaps if gap.strip()))
        return FitResult(None, PARSE_ERROR)

    async def aclose(self) -> None:
        """Close the LLM client's connections."""
        if self._llm is not None:
            await self._llm.aclose()
