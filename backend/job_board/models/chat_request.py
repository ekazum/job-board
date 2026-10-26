"""Request body for POST /api/chat."""

from pydantic import BaseModel, Field

THREAD_ID = r"^[\w-]{1,64}$"


class ChatRequest(BaseModel):
    """A message for the chat agent; thread_id continues a conversation (none starts a new one)."""

    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, pattern=THREAD_ID)
