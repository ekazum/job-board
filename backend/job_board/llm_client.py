"""The single LLM entry point: an OpenAI-compatible chat endpoint chosen in config.yaml. Nothing else imports openai."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx2
import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from openai.types.shared_params import ResponseFormatJSONObject

from job_board.llm_error import LlmError
from job_board.llm_settings import LlmSettings
from job_board.utils.prompt_files import prompt

NO_KEY = "NONE"
DUMMY_KEY = "ollama"  # OpenAI-compatible servers that need no key (Ollama) still expect the header
JSON_OBJECT: ResponseFormatJSONObject = {"type": "json_object"}


class LlmClient:
    """Sends one prompt at a time to Ollama, Groq, GitHub Models, Anthropic or OpenAI through their
    OpenAI-compatible APIs. Every request uses temperature 0 and the scoring system prompt, which holds the JSON
    schema of the answer (prompts/score_system.txt); providers with json_mode also get
    response_format=json_object. At most `concurrency` requests are in flight (1 for a local CPU model).
    http_client, for tests, is an httpx2.AsyncClient: the HTTP library the openai SDK is built on."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        concurrency: int,
        json_mode: bool,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._json_mode = json_mode
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    @classmethod
    def from_settings(
        cls, settings: LlmSettings, environ: Mapping[str, str], http_client: httpx2.AsyncClient | None = None
    ) -> LlmClient:
        """The client for settings.provider; ValueError when it is not configured or its API key is not set."""
        provider = next((entry for entry in settings.providers if entry.name == settings.provider), None)
        if provider is None:
            raise ValueError(f"provider {settings.provider!r} is not listed under providers in config.yaml")
        if provider.api_key_env.upper() == NO_KEY:
            api_key = DUMMY_KEY
        else:
            api_key = environ.get(provider.api_key_env, "").strip()
            if not api_key:
                raise ValueError(f"{provider.api_key_env} is not set; add it to .env for provider {provider.name!r}")
        return cls(
            provider=provider.name,
            base_url=provider.base_url,
            api_key=api_key,
            model=provider.model or settings.model,
            timeout_seconds=settings.request_timeout_s,
            max_retries=settings.max_retries,
            concurrency=provider.concurrency,
            json_mode=provider.json_mode,
            http_client=http_client,
        )

    @property
    def provider(self) -> str:
        """Name of the provider this client talks to."""
        return self._provider

    @property
    def model(self) -> str:
        """Model sent with every request."""
        return self._model

    async def score(self, prompt_text: str) -> str:
        """Send one prompt and return the model's raw answer (a JSON object when the model follows the schema)."""
        system: ChatCompletionSystemMessageParam = {"role": "system", "content": prompt("score_system.txt")}
        user: ChatCompletionUserMessageParam = {"role": "user", "content": prompt_text}
        async with self._semaphore:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[system, user],
                    temperature=0,
                    response_format=JSON_OBJECT if self._json_mode else openai.omit,
                )
            except openai.OpenAIError as error:
                raise LlmError(f"{self._provider}: {type(error).__name__}: {error}") from error
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LlmError(f"{self._provider}: the answer had no content")
        return content

    async def aclose(self) -> None:
        """Close the underlying HTTP connections."""
        await self._client.close()
