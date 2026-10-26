"""A saved chat conversation."""

from pydantic import BaseModel

from job_board.models.chat_line import ChatLine


class ChatHistory(BaseModel):
    """The conversation thread_id, oldest line first."""

    thread_id: str
    lines: list[ChatLine]
