"""The LangChain chat model the chat window talks to."""

from collections.abc import Callable, Mapping

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from job_board.config.app_config import AppConfig
from job_board.config.provider_credentials import ProviderCredentials

OLLAMA = "ollama"
OPENAI_SUFFIX = "/v1"
TEMPERATURE = 0.2


class ChatModelFactory:
    """Builds the model for config.yaml's chat section, read again for every message so an edit applies without a
    restart. Ollama is reached through its own API (ChatOllama), where chat.num_ctx sets the context window (its
    OpenAI-compatible endpoint cannot); every other provider through its OpenAI-compatible endpoint (ChatOpenAI),
    with its API key from .env. A provider that needs its own LangChain class is one more branch in create()."""

    def __init__(self, config_loader: Callable[[], AppConfig], environ: Mapping[str, str]) -> None:
        self._config_loader = config_loader
        self._environ = environ

    def create(self) -> BaseChatModel:
        """The chat model; ValueError when the provider is not configured or its API key is not set."""
        config = self._config_loader()
        settings = config.chat
        provider = ProviderCredentials.find(config.llm.providers, settings.provider)
        if provider.name == OLLAMA:
            native_url = provider.base_url.rstrip("/").removesuffix(OPENAI_SUFFIX)
            return ChatOllama(model=settings.model, base_url=native_url, num_ctx=settings.num_ctx, temperature=TEMPERATURE)
        return ChatOpenAI(
            model=settings.model,
            base_url=provider.base_url,
            api_key=SecretStr(ProviderCredentials.api_key(provider, self._environ)),
            temperature=TEMPERATURE,
        )
