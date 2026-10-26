"""Request body for POST /api/chat/{thread_id}/resume."""

from pydantic import BaseModel


class ChatResume(BaseModel):
    """The user's answer to the changes the agent asked to make: approve makes them, false cancels them."""

    approve: bool
