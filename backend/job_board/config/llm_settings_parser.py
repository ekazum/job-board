"""Read the llm, chat and providers sections of config.yaml."""

from job_board.config.chat_settings import ChatSettings
from job_board.config.llm_provider import LlmProvider
from job_board.config.llm_settings import DEFAULT_PROVIDERS, LlmSettings
from job_board.utils.json_values import as_dict

DEFAULTS = LlmSettings()
CHAT_DEFAULTS = ChatSettings()


class LlmSettingsParser:
    """Validates the llm section (provider, model, threshold, max_text_chars, request_timeout_s, max_retries) and the
    providers section ({name: {base_url, api_key_env, concurrency?, json_mode?, model?}}). Missing sections fall back
    to the defaults in LlmSettings; llm.provider must name one of the providers. parse_chat does the same for the chat
    section (ChatSettings)."""

    @staticmethod
    def parse(llm_section: object, providers_section: object) -> LlmSettings:
        """LlmSettings from the two YAML values (None when a section is absent)."""
        llm = LlmSettingsParser._section(llm_section, "llm")
        providers = LlmSettingsParser._providers(providers_section)
        settings = LlmSettings(
            provider=LlmSettingsParser._text(llm.get("provider"), "llm.provider", DEFAULTS.provider),
            model=LlmSettingsParser._text(llm.get("model"), "llm.model", DEFAULTS.model),
            threshold=LlmSettingsParser._integer(llm.get("threshold"), "llm.threshold", DEFAULTS.threshold),
            max_text_chars=LlmSettingsParser._integer(llm.get("max_text_chars"), "llm.max_text_chars", DEFAULTS.max_text_chars),
            request_timeout_s=float(
                LlmSettingsParser._integer(llm.get("request_timeout_s"), "llm.request_timeout_s", int(DEFAULTS.request_timeout_s))
            ),
            max_retries=LlmSettingsParser._integer(llm.get("max_retries"), "llm.max_retries", DEFAULTS.max_retries),
            providers=providers,
        )
        if settings.provider not in {provider.name for provider in providers}:
            raise ValueError(f"config 'llm.provider' is {settings.provider!r}, which is not listed under providers")
        return settings

    @staticmethod
    def parse_chat(chat_section: object, providers: tuple[LlmProvider, ...]) -> ChatSettings:
        """ChatSettings from the chat section (None when absent); chat.provider must name one of the providers."""
        chat = LlmSettingsParser._section(chat_section, "chat")
        settings = ChatSettings(
            provider=LlmSettingsParser._text(chat.get("provider"), "chat.provider", CHAT_DEFAULTS.provider),
            model=LlmSettingsParser._text(chat.get("model"), "chat.model", CHAT_DEFAULTS.model),
            num_ctx=LlmSettingsParser._integer(chat.get("num_ctx"), "chat.num_ctx", CHAT_DEFAULTS.num_ctx),
            max_steps=LlmSettingsParser._integer(chat.get("max_steps"), "chat.max_steps", CHAT_DEFAULTS.max_steps),
            history_tokens=LlmSettingsParser._integer(chat.get("history_tokens"), "chat.history_tokens", CHAT_DEFAULTS.history_tokens),
        )
        if settings.provider not in {provider.name for provider in providers}:
            raise ValueError(f"config 'chat.provider' is {settings.provider!r}, which is not listed under providers")
        return settings

    @staticmethod
    def _providers(value: object) -> tuple[LlmProvider, ...]:
        """The providers section, in file order."""
        if value is None:
            return DEFAULT_PROVIDERS
        section = LlmSettingsParser._section(value, "providers")
        providers: list[LlmProvider] = []
        for name, entry in section.items():
            key = f"providers.{name}"
            fields = LlmSettingsParser._section(entry, key)
            model = fields.get("model")
            providers.append(
                LlmProvider(
                    name=name,
                    base_url=LlmSettingsParser._text(fields.get("base_url"), f"{key}.base_url", None),
                    api_key_env=LlmSettingsParser._text(fields.get("api_key_env"), f"{key}.api_key_env", None),
                    concurrency=LlmSettingsParser._integer(fields.get("concurrency"), f"{key}.concurrency", 5),
                    json_mode=LlmSettingsParser._flag(fields.get("json_mode"), f"{key}.json_mode"),
                    model=None if model is None else LlmSettingsParser._text(model, f"{key}.model", None),
                )
            )
        if not providers:
            raise ValueError("config 'providers' is empty")
        return tuple(providers)

    @staticmethod
    def _section(value: object, key: str) -> dict[str, object]:
        """An optional mapping."""
        if value is None:
            return {}
        section = as_dict(value)
        if section is None:
            raise ValueError(f"config '{key}' must be a mapping")
        return section

    @staticmethod
    def _text(value: object, key: str, default: str | None) -> str:
        """A non-blank string; the default when absent (required when the default is None)."""
        if value is None and default is not None:
            return default
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config '{key}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _integer(value: object, key: str, default: int) -> int:
        """A non-negative integer; the default when absent."""
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"config '{key}' must be a non-negative integer")
        return value

    @staticmethod
    def _flag(value: object, key: str) -> bool:
        """true/false; false when absent."""
        if value is None:
            return False
        if not isinstance(value, bool):
            raise ValueError(f"config '{key}' must be true or false")
        return value
