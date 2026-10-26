"""HTTP endpoints for the Settings view."""

import os
import time
from collections.abc import Callable, Mapping

from fastapi import APIRouter, HTTPException, status

from job_board.config.app_config import AppConfig
from job_board.config.config_editor import ConfigEditor
from job_board.config.llm_settings import LlmSettings
from job_board.config.provider_credentials import NO_KEY
from job_board.llm.llm_client import LlmClient
from job_board.llm.llm_error import LlmError
from job_board.models.llm_provider_choice import LlmProviderChoice
from job_board.models.llm_settings_view import LlmSettingsView
from job_board.models.llm_test_result import LlmTestResult
from job_board.utils.prompt_files import prompt

ClientFactory = Callable[[LlmSettings, Mapping[str, str]], LlmClient]


class SettingsRoutes:
    """GET /api/settings/llm, PUT /api/settings/llm/provider (rewrites llm.provider in config.yaml), and
    POST /api/settings/llm/test (sends prompts/settings_test.txt and reports latency and the raw answer).
    config.yaml is re-read on every request, so a switch applies at once."""

    def __init__(
        self,
        config_loader: Callable[[], AppConfig],
        config_editor: ConfigEditor,
        environ: Mapping[str, str] | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._config_loader = config_loader
        self._config_editor = config_editor
        self._environ = os.environ if environ is None else environ
        self._client_factory = client_factory or LlmClient.from_settings

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/settings", tags=["settings"])
        router.add_api_route("/llm", self.get_llm_settings, methods=["GET"])
        router.add_api_route("/llm/provider", self.set_llm_provider, methods=["PUT"])
        router.add_api_route("/llm/test", self.test_llm, methods=["POST"])
        return router

    def get_llm_settings(self) -> LlmSettingsView:
        """The active provider and model from config.yaml."""
        settings = self._config_loader().llm
        provider = next(entry for entry in settings.providers if entry.name == settings.provider)
        no_key = provider.api_key_env.upper() == NO_KEY
        return LlmSettingsView(
            provider=provider.name,
            model=provider.model or settings.model,
            base_url=provider.base_url,
            api_key_env=provider.api_key_env,
            api_key_set=no_key or bool(self._environ.get(provider.api_key_env, "").strip()),
            concurrency=provider.concurrency,
            json_mode=provider.json_mode,
            threshold=settings.threshold,
            max_text_chars=settings.max_text_chars,
            providers=[entry.name for entry in settings.providers],
        )

    def set_llm_provider(self, body: LlmProviderChoice) -> LlmSettingsView:
        """Switch llm.provider in config.yaml (comments and layout are kept); 422 for a provider not listed."""
        names = [entry.name for entry in self._config_loader().llm.providers]
        if body.provider not in names:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown provider {body.provider!r}; one of {names}")
        self._config_editor.set_llm_provider(body.provider)
        return self.get_llm_settings()

    async def test_llm(self) -> LlmTestResult:
        """Send a tiny scoring prompt to the active provider; failures are reported in the result, not as HTTP errors."""
        settings = self._config_loader().llm
        started = time.monotonic()
        try:
            client = self._client_factory(settings, self._environ)
        except ValueError as error:
            return LlmTestResult(ok=False, provider=settings.provider, model=settings.model, latency_ms=0, raw="", error=str(error))
        try:
            raw = await client.score(prompt("settings_test.txt"))
            error_text: str | None = None
        except LlmError as error:
            raw, error_text = "", str(error)
        finally:
            await client.aclose()
        latency_ms = round((time.monotonic() - started) * 1000)
        return LlmTestResult(
            ok=error_text is None,
            provider=client.provider,
            model=client.model,
            latency_ms=latency_ms,
            raw=raw,
            error=error_text,
        )
