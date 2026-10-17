"""Error for an LLM request that failed."""


class LlmError(Exception):
    """The provider could not be reached, refused the request, or answered without content. Raised by LlmClient
    so callers never depend on the provider SDK's exception types."""
