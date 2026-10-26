"""Settings API: show the active LLM provider, switch it in config.yaml, and test it."""

from collections.abc import Iterator, Mapping
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from job_board.api.settings_routes import SettingsRoutes
from job_board.app_factory import AppFactory
from job_board.config.app_config import AppConfig
from job_board.config.config_editor import ConfigEditor
from job_board.config.llm_settings import LlmSettings
from job_board.llm.llm_client import LlmClient
from job_board.llm.llm_error import LlmError

CONFIG = """db_path: data/job_board.db
llm:
  provider: ollama   # ollama | groq
  model: qwen2.5:7b
providers:
  ollama: {base_url: http://localhost:11434/v1, api_key_env: NONE, concurrency: 1, json_mode: true}
  groq: {base_url: https://api.groq.com/openai/v1, api_key_env: GROQ_API_KEY, concurrency: 5}
"""


def _fake_client(answer: str | Exception) -> MagicMock:
    client = MagicMock(spec=LlmClient)
    client.provider, client.model = "ollama", "qwen2.5:7b"
    if isinstance(answer, Exception):
        client.score.side_effect = answer
    else:
        client.score.return_value = answer
    return client


def _app(tmp_path: Path, environ: Mapping[str, str], client: MagicMock | None = None) -> TestClient:
    path = tmp_path / "config.yaml"
    if not path.exists():
        path.write_text(CONFIG, encoding="utf-8")
    loader = partial(AppConfig.from_yaml, path)

    def factory(settings: LlmSettings, env: Mapping[str, str]) -> LlmClient:
        if client is None:
            return LlmClient.from_settings(settings, env)
        return client

    routes = SettingsRoutes(loader, ConfigEditor(path), environ, factory)
    return TestClient(AppFactory(loader, tmp_path / "no-dist", settings_routes=routes, config_path=path).build())


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _app(tmp_path, {}) as test_client:
        yield test_client


def test_shows_the_active_provider(client: TestClient) -> None:
    body = client.get("/api/settings/llm").json()
    assert (body["provider"], body["model"], body["base_url"]) == ("ollama", "qwen2.5:7b", "http://localhost:11434/v1")
    assert (body["api_key_set"], body["concurrency"], body["json_mode"], body["providers"]) == (True, 1, True, ["ollama", "groq"])


def test_switching_provider_rewrites_config_and_reloads(tmp_path: Path) -> None:
    with _app(tmp_path, {"GROQ_API_KEY": "gsk_test"}) as test_client:
        switched = test_client.put("/api/settings/llm/provider", json={"provider": "groq"})
        assert (switched.status_code, switched.json()["provider"], switched.json()["api_key_set"]) == (200, "groq", True)
        assert test_client.get("/api/settings/llm").json()["provider"] == "groq"
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "  provider: groq   # ollama | groq\n" in text  # the comment is kept
    assert text == CONFIG.replace("provider: ollama ", "provider: groq ")


def test_unknown_provider_is_422_and_config_unchanged(tmp_path: Path) -> None:
    with _app(tmp_path, {}) as test_client:
        assert test_client.put("/api/settings/llm/provider", json={"provider": "nope"}).status_code == 422
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == CONFIG


def test_test_button_reports_latency_and_raw_answer(tmp_path: Path) -> None:
    fake = _fake_client('{"score": 9, "reason": "LLM infrastructure"}')
    with _app(tmp_path, {}, fake) as test_client:
        body = test_client.post("/api/settings/llm/test").json()
    assert (body["ok"], body["raw"], body["error"], body["provider"]) == (True, '{"score": 9, "reason": "LLM infrastructure"}', None, "ollama")
    assert body["latency_ms"] >= 0
    fake.aclose.assert_awaited_once_with()


def test_test_button_reports_provider_errors_without_failing(tmp_path: Path) -> None:
    fake = _fake_client(LlmError("ollama: APIConnectionError: Connection error."))
    with _app(tmp_path, {}, fake) as test_client:
        response = test_client.post("/api/settings/llm/test")
    assert (response.status_code, response.json()["ok"]) == (200, False)
    assert "Connection error" in response.json()["error"]


def test_test_button_reports_a_missing_api_key(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(CONFIG.replace("provider: ollama ", "provider: groq "), encoding="utf-8")
    with _app(tmp_path, {}) as test_client:
        body = test_client.post("/api/settings/llm/test").json()
    assert (body["ok"], body["provider"]) == (False, "groq")
    assert "GROQ_API_KEY is not set" in body["error"]
