"""Value object for the llm and providers sections of config.yaml."""

from dataclasses import dataclass, field

from job_board.config.llm_provider import LlmProvider

DEFAULT_PROVIDERS: tuple[LlmProvider, ...] = (
    LlmProvider("ollama", "http://localhost:11434/v1", "NONE", concurrency=1, json_mode=True),
    LlmProvider("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    LlmProvider("github", "https://models.inference.ai.azure.com", "GITHUB_TOKEN"),
    LlmProvider("anthropic", "https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY"),
    LlmProvider("openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
)


@dataclass(frozen=True)
class LlmSettings:
    """Which provider and model score postings, and how. threshold is the fit below which a card shows its score as
    low (the score never moves a card); max_text_chars how much of a description the scorer sends."""

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    threshold: int = 6
    max_text_chars: int = 3000
    request_timeout_s: float = 120.0
    max_retries: int = 2
    providers: tuple[LlmProvider, ...] = field(default=DEFAULT_PROVIDERS)
