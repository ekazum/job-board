"""LLM settings as shown in the Settings view."""

from pydantic import BaseModel


class LlmSettingsView(BaseModel):
    """The active provider and how it is reached; api_key_set tells whether its .env variable has a value
    (the key itself is never sent to the browser)."""

    provider: str
    model: str
    base_url: str
    api_key_env: str
    api_key_set: bool
    concurrency: int
    json_mode: bool
    threshold: int
    max_text_chars: int
    providers: list[str]
