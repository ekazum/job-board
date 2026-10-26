"""The chat graph's state."""

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class ChatState(BaseModel):
    """The conversation so far, oldest first; the messages a node returns are appended (add_messages)."""

    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list[AnyMessage])
