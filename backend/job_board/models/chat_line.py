"""One line of a saved chat conversation."""

from typing import Literal

from pydantic import BaseModel


class ChatLine(BaseModel):
    """role is user (a question), assistant (an answer) or tool ("search_postings · 12 found")."""

    role: Literal["user", "assistant", "tool"]
    text: str
