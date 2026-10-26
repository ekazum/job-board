"""The chat agent's LangGraph graph."""

from collections.abc import Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from job_board.chat.chat_state import ChatState

AGENT = "agent"
TOOLS = "tools"


class ChatGraph:
    """START -> agent -> (the model asked for tools) -> tools -> agent ... -> (it answered) -> END.

    The agent node sends the system prompt, the earlier conversation cut to its last history_tokens (questions and
    answers only: earlier tool calls and results are left out, as a small local model's context is short) and the
    current question with its tool calls and results so far. The tools node runs what the model asked for; a tool
    that fails tells the model why. The checkpointer saves each conversation (thread) after every step.
    """

    def __init__(
        self, model: BaseChatModel, tools: Sequence[BaseTool], system_prompt: Callable[[], str], history_tokens: int
    ) -> None:
        self._model = model.bind_tools(tools)
        self._tools = tools
        self._system_prompt = system_prompt
        self._history_tokens = history_tokens

    def compile(self, checkpointer: BaseCheckpointSaver[str]) -> CompiledStateGraph[ChatState]:
        """The runnable graph, saving to checkpointer."""
        graph = StateGraph(ChatState)
        graph.add_node(AGENT, self._answer)
        graph.add_node(TOOLS, ToolNode(self._tools))
        graph.add_edge(START, AGENT)
        graph.add_conditional_edges(AGENT, tools_condition)
        graph.add_edge(TOOLS, AGENT)
        return graph.compile(checkpointer=checkpointer)

    async def _answer(self, state: ChatState) -> dict[str, list[AnyMessage]]:
        """One model call: an answer, or a request for tools."""
        messages = state.messages
        current = max((index for index, message in enumerate(messages) if isinstance(message, HumanMessage)), default=0)
        earlier = self._recent([message for message in messages[:current] if self._is_dialogue(message)])
        reply: AnyMessage = await self._model.ainvoke([SystemMessage(self._system_prompt()), *earlier, *messages[current:]])
        return {"messages": [reply]}

    def _recent(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """The latest messages that fit in history_tokens (about 4 characters a token), starting with a question."""
        kept: list[AnyMessage] = []
        budget = self._history_tokens
        for message in reversed(messages):
            budget -= count_tokens_approximately([message])
            if budget < 0:
                break
            kept.append(message)
        kept.reverse()
        while kept and not isinstance(kept[0], HumanMessage):
            kept.pop(0)
        return kept

    @staticmethod
    def _is_dialogue(message: AnyMessage) -> bool:
        """A question, or an answer in words (not a request for tools)."""
        if isinstance(message, HumanMessage):
            return True
        return isinstance(message, AIMessage) and not message.tool_calls and bool(message.text)
