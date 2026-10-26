"""Which provider entry a setting names, and the API key to send it."""

from collections.abc import Mapping

from job_board.config.llm_provider import LlmProvider

NO_KEY = "NONE"
DUMMY_KEY = "ollama"  # OpenAI-compatible servers that need no key (Ollama) still expect the header


class ProviderCredentials:
    """Looks a provider up by name and reads its API key from the environment (the repo's .env)."""

    @staticmethod
    def find(providers: tuple[LlmProvider, ...], name: str) -> LlmProvider:
        """The entry called name; ValueError when it is not configured."""
        provider = next((entry for entry in providers if entry.name == name), None)
        if provider is None:
            raise ValueError(f"provider {name!r} is not listed under providers in config.yaml")
        return provider

    @staticmethod
    def api_key(provider: LlmProvider, environ: Mapping[str, str]) -> str:
        """The key in the variable api_key_env names (a dummy for NONE); ValueError when that variable is not set."""
        if provider.api_key_env.upper() == NO_KEY:
            return DUMMY_KEY
        api_key = environ.get(provider.api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"{provider.api_key_env} is not set; add it to .env for provider {provider.name!r}")
        return api_key
