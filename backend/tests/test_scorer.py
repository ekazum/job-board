"""Scorer with a fake LlmClient: prompt contents, Pydantic parsing, one retry on bad JSON, fallbacks."""

from unittest.mock import MagicMock

import pytest

from job_board.database import Database
from job_board.fit_result import FitResult
from job_board.llm_client import LlmClient
from job_board.llm_error import LlmError
from job_board.llm_settings import LlmSettings
from job_board.models.profile_patch import ProfilePatch
from job_board.profile_repository import ProfileRepository
from job_board.scorer import Scorer
from job_board.utils.prompt_files import prompt

GOOD = '{"relevant": true, "fit": 8, "reason": "Strong ML platform match", "gaps": ["Kubernetes", " "]}'


def _fake_llm(*answers: str | Exception) -> MagicMock:
    llm = MagicMock(spec=LlmClient)
    llm.score.side_effect = list(answers)
    return llm


def _scorer(database: Database, llm: MagicMock, cv: str = "Ten years of Python and ML.", max_chars: int = 3000) -> Scorer:
    profiles = ProfileRepository(database)
    if cv:
        profiles.update(ProfilePatch(cv_text=cv, targets="AI research roles in Israel"))
    return Scorer(llm, profiles, max_chars)


async def _score(scorer: Scorer, text: str = "Build LLM serving.") -> FitResult:
    return await scorer.score(title="ML Engineer", company="Acme", location="Tel Aviv, Israel", text=text)


@pytest.mark.anyio
async def test_valid_answer_is_parsed(database: Database) -> None:
    llm = _fake_llm(GOOD)
    result = await _score(_scorer(database, llm))
    assert result == FitResult(8, "Strong ML platform match", ("Kubernetes",))
    sent = llm.score.call_args.args[0]
    assert "Ten years of Python and ML." in sent and "AI research roles in Israel" in sent
    assert "Title: ML Engineer" in sent and "Company: Acme" in sent and "Location: Tel Aviv, Israel" in sent


@pytest.mark.anyio
async def test_description_is_cut_to_max_text_chars(database: Database) -> None:
    llm = _fake_llm(GOOD)
    await _score(_scorer(database, llm, max_chars=10), text="0123456789ABCDEFGHIJ")
    sent = llm.score.call_args.args[0]
    assert "0123456789" in sent and "ABCDEFGHIJ" not in sent


@pytest.mark.anyio
async def test_bad_json_is_retried_once(database: Database) -> None:
    llm = _fake_llm("Sure! Here is the score: 8", GOOD)
    assert (await _score(_scorer(database, llm))).fit == 8
    assert llm.score.await_count == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "answers",
    [
        ("not json", "still not json"),
        ('{"relevant": true, "fit": 11, "reason": "x"}', '{"fit": 5}'),  # out of range, then missing fields
    ],
)
async def test_two_bad_answers_give_parse_error(database: Database, answers: tuple[str, str]) -> None:
    llm = _fake_llm(*answers)
    assert await _score(_scorer(database, llm)) == FitResult(None, "parse error")
    assert llm.score.await_count == 2


@pytest.mark.anyio
async def test_not_relevant_scores_zero(database: Database) -> None:
    llm = _fake_llm('{"relevant": false, "fit": 7, "reason": "Located in Berlin", "gaps": []}')
    assert await _score(_scorer(database, llm)) == FitResult(0, "Located in Berlin")


@pytest.mark.anyio
async def test_without_a_profile_the_llm_is_not_called(database: Database) -> None:
    llm = _fake_llm(GOOD)
    assert await _score(_scorer(database, llm, cv="")) == FitResult(None, "no profile")
    llm.score.assert_not_awaited()


@pytest.mark.anyio
async def test_llm_failure_is_recorded_as_reason(database: Database) -> None:
    llm = _fake_llm(LlmError("ollama: APIConnectionError: Connection error."))
    result = await _score(_scorer(database, llm))
    assert result.fit is None
    assert result.reason == "llm error: ollama: APIConnectionError: Connection error."


@pytest.mark.anyio
async def test_provider_that_cannot_be_set_up_gives_reason(database: Database) -> None:
    ProfileRepository(database).update(ProfilePatch(cv_text="CV"))
    scorer = Scorer.from_settings(LlmSettings(provider="groq"), ProfileRepository(database), {})
    result = await _score(scorer)
    assert result.fit is None and result.reason is not None and "GROQ_API_KEY is not set" in result.reason


def test_system_prompt_states_the_rubric_and_schema() -> None:
    system = prompt("score_system.txt")
    for phrase in ("Hard requirements first", "Israel", "remote", "intern, student and junior", '"relevant"', '"fit"', '"gaps"'):
        assert phrase in system
