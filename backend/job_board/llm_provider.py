"""Value object for one LLM provider entry in config.yaml."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmProvider:
    """An OpenAI-compatible endpoint. api_key_env names the .env variable holding the key ("NONE": no key needed,
    a dummy one is sent). concurrency caps requests in flight (1 for a local CPU model). json_mode asks the
    endpoint for response_format=json_object. model, when set, overrides llm.model for this provider."""

    name: str
    base_url: str
    api_key_env: str
    concurrency: int = 5
    json_mode: bool = False
    model: str | None = None
