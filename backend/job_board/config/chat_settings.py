"""Value object for the chat section of config.yaml."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatSettings:
    """The chat window's model: provider names an entry under providers, model the model it runs. num_ctx is the
    context window Ollama gives the model, in tokens (the system prompt, the tools, the history and the tool results
    must fit in it); other providers ignore it. max_steps caps the model and tool steps of one answer; history_tokens
    is how much of the earlier conversation is sent along with each message."""

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    num_ctx: int = 8192
    max_steps: int = 12
    history_tokens: int = 3000
