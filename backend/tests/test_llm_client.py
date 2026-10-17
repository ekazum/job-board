"""LlmClient against a fake OpenAI-compatible /chat/completions endpoint (no network, no Ollama needed)."""

import asyncio
import json

import httpx2
import pytest

from job_board.llm_client import LlmClient
from job_board.llm_error import LlmError
from job_board.llm_provider import LlmProvider
from job_board.llm_settings import LlmSettings
from job_board.utils.prompt_files import prompt

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
ANSWER = '{"score": 8, "reason": "ML engineering role"}'


def _completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen2.5:7b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }


def _client(handler: httpx2.MockTransport, settings: LlmSettings | None = None, environ: dict[str, str] | None = None) -> LlmClient:
    chosen = settings or LlmSettings(max_retries=0)
    return LlmClient.from_settings(chosen, environ or {}, http_client=httpx2.AsyncClient(transport=handler))


@pytest.mark.anyio
async def test_ollama_request_uses_json_mode_temperature_zero_and_the_schema_prompt() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=_completion(ANSWER))

    client = _client(httpx2.MockTransport(handler))
    try:
        assert await client.score("Job title: ML Engineer") == ANSWER
    finally:
        await client.aclose()
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == OLLAMA_URL
    assert request.headers["authorization"] == "Bearer ollama"  # dummy key for a provider that needs none
    assert (body["model"], body["temperature"], body["response_format"]) == ("qwen2.5:7b", 0, {"type": "json_object"})
    assert body["messages"] == [
        {"role": "system", "content": prompt("score_system.txt")},
        {"role": "user", "content": "Job title: ML Engineer"},
    ]


@pytest.mark.anyio
async def test_hosted_provider_sends_its_key_and_no_response_format() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=_completion(ANSWER))

    settings = LlmSettings(provider="groq", model="some-model", max_retries=0)
    client = _client(httpx2.MockTransport(handler), settings, {"GROQ_API_KEY": "gsk_test"})
    try:
        await client.score("x")
    finally:
        await client.aclose()
    assert str(seen[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer gsk_test"
    assert "response_format" not in json.loads(seen[0].content)


@pytest.mark.anyio
async def test_provider_model_overrides_llm_model() -> None:
    providers = (LlmProvider("local", "http://localhost:9/v1", "NONE", model="llama3.2:3b"),)
    settings = LlmSettings(provider="local", model="qwen2.5:7b", providers=providers, max_retries=0)
    client = _client(httpx2.MockTransport(lambda request: httpx2.Response(200, json=_completion(ANSWER))), settings)
    assert (client.provider, client.model) == ("local", "llama3.2:3b")
    await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 404, 500])
async def test_provider_errors_become_llm_error(status: int) -> None:
    client = _client(httpx2.MockTransport(lambda request: httpx2.Response(status, json={"error": {"message": "nope"}})))
    try:
        with pytest.raises(LlmError, match="ollama"):
            await client.score("x")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_unreachable_server_becomes_llm_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    client = _client(httpx2.MockTransport(refuse))
    try:
        with pytest.raises(LlmError, match="Connection"):
            await client.score("x")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_empty_answer_is_an_error() -> None:
    client = _client(httpx2.MockTransport(lambda request: httpx2.Response(200, json=_completion(""))))
    try:
        with pytest.raises(LlmError, match="no content"):
            await client.score("x")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_ollama_runs_one_request_at_a_time() -> None:
    in_flight = peak = 0

    async def slow(request: httpx2.Request) -> httpx2.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx2.Response(200, json=_completion(ANSWER))

    client = _client(httpx2.MockTransport(slow))
    try:
        await asyncio.gather(*(client.score(f"job {index}") for index in range(4)))
    finally:
        await client.aclose()
    assert peak == 1  # concurrency: 1 for the local CPU model


def test_missing_api_key_and_unknown_provider_are_reported() -> None:
    with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
        LlmClient.from_settings(LlmSettings(provider="groq"), {})
    with pytest.raises(ValueError, match="not listed under providers"):
        LlmClient.from_settings(LlmSettings(provider="nope"), {})
