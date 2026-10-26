"""Re-score: the profile's keywords and location first, the background job and its progress, one posting at a time,
and the API."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from job_board.api.rescore_routes import RescoreRoutes
from job_board.app_factory import AppFactory
from job_board.config.app_config import AppConfig
from job_board.enums.outcome import Outcome
from job_board.enums.source import Source
from job_board.enums.status import Status
from job_board.llm.fit_result import FitResult
from job_board.llm.scorer import Scorer
from job_board.models.posting import Posting
from job_board.models.profile import Profile
from job_board.rules.profile_sweep import ProfileSweep
from job_board.runs.rescore_job import RescoreJob
from job_board.storage.database import Database
from job_board.storage.posting_repository import PostingRepository

ISRAEL = Profile(location="Israel")


def _fake_scorer(fits: dict[str, FitResult]) -> MagicMock:
    """Scores by title; MagicMock(spec=Scorer) makes score/aclose AsyncMocks."""
    scorer = MagicMock(spec=Scorer)

    async def score(*, title: str, company: str, text: str) -> FitResult:
        del company, text
        return fits[title]

    scorer.score.side_effect = score
    return scorer


def _add(
    database: Database, title: str, location: str = "Tel Aviv, Israel", source: Source = Source.GREENHOUSE, **changes: object
) -> Posting:
    postings = PostingRepository(database)
    posting, _ = postings.insert(
        source=source, external_id=title, company="Acme", title=title, url=f"https://x/{title}", text="", location=location
    )
    if changes:
        saved = postings.save(posting.model_copy(update=changes))
        assert saved is not None
        return saved
    return posting


def _job(database: Database, scorer: MagicMock, profile: Profile = ISRAEL) -> RescoreJob:
    postings = PostingRepository(database)
    return RescoreJob(postings, lambda: scorer, ProfileSweep(postings, lambda: profile))


async def _finish(job: RescoreJob) -> None:
    while job.running:
        await asyncio.sleep(0.01)


@pytest.mark.anyio
async def test_rescore_all_scores_new_and_unscored_postings_with_progress(database: Database) -> None:
    _add(database, "Strong")
    _add(database, "Weak")
    _add(database, "Applied, unscored", status=Status.APPLIED)
    fits = {"Strong": FitResult(9, "great"), "Weak": FitResult(2, "far off"), "Applied, unscored": FitResult(4, "meh")}
    scorer = _fake_scorer(fits)
    job = _job(database, scorer)
    assert job.start() is True
    assert job.status().total == 3
    while job.running:
        await asyncio.sleep(0.01)
    assert (job.status().done, job.status().total, job.status().error) == (3, 3, None)
    by_title = {posting.title: posting for posting in PostingRepository(database).list_all()}
    assert (by_title["Strong"].status, by_title["Strong"].fit) == (Status.NEW, 9)
    assert (by_title["Weak"].status, by_title["Weak"].outcome, by_title["Weak"].fit_reason) == (Status.NEW, None, "far off")  # stays put
    assert (by_title["Applied, unscored"].status, by_title["Applied, unscored"].fit) == (Status.APPLIED, 4)  # your progress is kept
    scorer.aclose.assert_awaited_once_with()


@pytest.mark.anyio
async def test_a_reopened_posting_is_rescored_but_not_archived_again(database: Database) -> None:
    reopened = _add(database, "Reopened")
    PostingRepository(database).save_fit(reopened.id, FitResult(3, "old"), Status.NEW, None)  # scored before, back in New
    job = _job(database, _fake_scorer({"Reopened": FitResult(2, "still weak")}))
    job.start()
    while job.running:
        await asyncio.sleep(0.01)
    stored = PostingRepository(database).get(reopened.id)
    assert stored is not None and (stored.status, stored.fit, stored.fit_reason) == (Status.NEW, 2, "still weak")


@pytest.mark.anyio
async def test_only_one_rescore_at_a_time(database: Database) -> None:
    _add(database, "One")
    release = asyncio.Event()
    scorer = MagicMock(spec=Scorer)

    async def slow(*, title: str, company: str, text: str) -> FitResult:
        del title, company, text
        await release.wait()
        return FitResult(7, "ok")

    scorer.score.side_effect = slow
    job = _job(database, scorer)
    assert job.start() is True
    await asyncio.sleep(0)
    assert (job.start(), job.status().running) == (False, True)
    assert job.apply_filters() is None  # not while scores are being written
    release.set()
    while job.running:
        await asyncio.sleep(0.01)
    assert job.start() is True  # a finished run can be started again


@pytest.mark.anyio
async def test_rescore_one_and_missing_posting(database: Database) -> None:
    posting = _add(database, "Single")
    job = _job(database, _fake_scorer({"Single": FitResult(8, "fits", ("Rust",))}))
    rescored = await job.rescore_one(posting.id)
    assert rescored is not None and (rescored.fit, rescored.fit_reason, rescored.fit_gaps) == (8, "fits", ["Rust"])
    assert await job.rescore_one(999) is None


# --- the keywords and the location rule -----------------------------------------------------------------


@pytest.mark.anyio
async def test_rescore_all_archives_postings_outside_the_location_without_an_llm_call(database: Database) -> None:
    _add(database, "In Israel", location="Herzliya")
    berlin = _add(database, "In Berlin", location="Berlin, Germany")
    scorer = _fake_scorer({"In Israel": FitResult(8, "fits")})  # "In Berlin" would raise KeyError if scored
    job = _job(database, scorer)
    assert job.start() is True
    assert job.status().total == 1
    await _finish(job)
    stored = PostingRepository(database).get(berlin.id)
    assert stored is not None
    assert (stored.status, stored.outcome, stored.fit, stored.fit_reason, stored.country) == (
        Status.CLOSED,
        Outcome.NOT_RELEVANT,
        None,
        "location: Berlin, Germany",
        "DE",
    )
    assert [call.kwargs["title"] for call in scorer.score.await_args_list] == ["In Israel"]


def test_sweep_moves_new_postings_brings_back_ones_that_now_pass_and_leaves_your_moves_alone(database: Database) -> None:
    postings = PostingRepository(database)
    haifa = _add(database, "Haifa", location="Haifa")
    berlin_new = _add(database, "Berlin, new", location="Berlin")
    berlin_applied = _add(database, "Berlin, applied", location="Berlin", status=Status.APPLIED)
    remote = _add(database, "Remote", location="Remote")
    profile = Profile(location="Germany")
    sweep = ProfileSweep(postings, lambda: profile)
    assert sweep.run().model_dump() == {"archived": 2, "restored": 0}  # Haifa and Remote
    profile = Profile(location="Israel", allow_fully_remote=True)
    assert sweep.run().model_dump() == {"archived": 1, "restored": 2}  # Berlin, new; Haifa and Remote come back
    by_id = {posting.id: posting for posting in postings.list_all()}
    assert (by_id[haifa.id].status, by_id[haifa.id].fit_reason, by_id[haifa.id].country) == (Status.NEW, None, "IL")
    assert (by_id[remote.id].status, by_id[remote.id].is_remote) == (Status.NEW, True)
    assert by_id[berlin_new.id].fit_reason == "location: Berlin"
    assert by_id[berlin_applied.id].status is Status.APPLIED  # your own move is never undone


def test_sweep_applies_the_job_title_keywords_and_leaves_pasted_postings_alone(database: Database) -> None:
    postings = PostingRepository(database)
    engineer = _add(database, "Senior AI Engineer")
    sales = _add(database, "Sales Lead")
    intern = _add(database, "AI Engineer Intern")
    pasted = _add(database, "Office Manager", location="", source=Source.MANUAL)
    profile = Profile(location="Israel", include_keywords=["AI + engineer"], exclude_keywords=["intern"])
    sweep = ProfileSweep(postings, lambda: profile)
    assert sweep.run().model_dump() == {"archived": 2, "restored": 0}
    reasons = {posting.id: (posting.status, posting.fit_reason) for posting in postings.list_all()}
    assert reasons[engineer.id] == (Status.NEW, None)
    assert reasons[sales.id] == (Status.CLOSED, "keywords: no wanted role in the title")
    assert reasons[intern.id] == (Status.CLOSED, 'keywords: excludes "intern"')
    assert reasons[pasted.id] == (Status.NEW, None)  # you added it yourself
    profile = Profile(location="Israel", include_keywords=["AI + engineer", "Sales Lead"], exclude_keywords=["intern"])
    assert sweep.run().model_dump() == {"archived": 0, "restored": 1}  # the sales lead comes back


@pytest.mark.anyio
async def test_rescore_one_outside_the_location_is_archived_unscored(database: Database) -> None:
    posting = _add(database, "Single", location="Paris, France")
    scorer = _fake_scorer({})
    rescored = await _job(database, scorer).rescore_one(posting.id)
    assert rescored is not None and (rescored.status, rescored.fit_reason) == (Status.CLOSED, "location: Paris, France")
    scorer.score.assert_not_awaited()


# --- API ------------------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    config = AppConfig(db_path=tmp_path / "data" / "job_board.db", companies=())
    database = Database(config.db_path)
    database.initialize()
    _add(database, "Strong")
    _add(database, "Elsewhere", location="Berlin")
    postings = PostingRepository(database)
    sweep = ProfileSweep(postings, lambda: ISRAEL)
    job = RescoreJob(postings, lambda: _fake_scorer({"Strong": FitResult(9, "great")}), sweep)
    app = AppFactory(lambda: config, tmp_path / "no-dist", database=database, rescore_routes=RescoreRoutes(job)).build()
    with TestClient(app) as test_client:
        yield test_client


def test_rescore_endpoints(client: TestClient) -> None:
    assert client.post("/api/rescore/filters").json() == {"archived": 1, "restored": 0}
    started = client.post("/api/rescore")
    assert (started.status_code, started.json()["total"]) == (202, 1)
    status = client.get("/api/rescore/status").json()
    for _ in range(100):
        if not status["running"]:
            break
        status = client.get("/api/rescore/status").json()
    assert (status["done"], status["total"]) == (1, 1)
    posting_id = next(posting["id"] for posting in client.get("/api/postings").json() if posting["title"] == "Strong")
    one = client.post(f"/api/rescore/{posting_id}")
    assert (one.status_code, one.json()["fit"], one.json()["fit_reason"]) == (200, 9, "great")
    assert client.post("/api/rescore/999").status_code == 404
