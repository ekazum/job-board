"""The chat agent's LangGraph graph."""

from collections.abc import Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolCall, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from job_board.chat.chat_state import ChatState

AGENT = "agent"
CONFIRM = "confirm"
TOOLS = "tools"
CANCELLED = "The user cancelled this; nothing was changed."  # the result of each call of a cancelled request
NOT_DONE = "Cancelled, not done: "  # the answer to it, before the changes in words
READ_ONLY_HINT = "readOnlyHint"  # the MCP annotation, in the metadata of each tool the adapter loads
Preview = Callable[[ToolCall], str | None]


class ChatGraph:
    """START -> agent -> (the model asked for tools) -> tools -> agent ... -> (it answered) -> END, with confirm
    before tools when a call would change the board.

    The agent node sends the system prompt, the earlier conversation cut to its last history_tokens (questions and
    answers only: earlier tool calls and results are left out, as a small local model's context is short) and the
    current question with its tool calls and results so far. The tools node runs what the model asked for; a tool
    that fails tells the model why. The checkpointer saves each conversation (thread) after every step.

    A tool not marked read-only changes the board. When the model calls one, the agent node also writes what each such
    call will do (preview) to pending, and the confirm node pauses the graph (interrupt) until the user answers:
    resumed with True the tools run; otherwise every call of the request is answered as cancelled, and the turn ends
    without another model call (False) or the agent answers the message the user sent instead (a str). A call preview
    gives None (it can only fail) needs no confirm.
    """

    def __init__(
        self,
        model: BaseChatModel,
        tools: Sequence[BaseTool],
        system_prompt: Callable[[], str],
        history_tokens: int,
        preview: Preview,
    ) -> None:
        self._model = model.bind_tools(tools)
        self._tools = tools
        self._system_prompt = system_prompt
        self._history_tokens = history_tokens
        self._preview = preview
        self.changing = frozenset(tool.name for tool in tools if not self._is_read_only(tool))

    def compile(self, checkpointer: BaseCheckpointSaver[str]) -> CompiledStateGraph[ChatState]:
        """The runnable graph, saving to checkpointer."""
        graph = StateGraph(ChatState)
        graph.add_node(AGENT, self._answer)
        graph.add_node(CONFIRM, self._confirm, destinations=(TOOLS, AGENT, END))
        graph.add_node(TOOLS, ToolNode(self._tools))
        graph.add_edge(START, AGENT)
        graph.add_conditional_edges(AGENT, self._next, [CONFIRM, TOOLS, END])
        graph.add_edge(TOOLS, AGENT)
        return graph.compile(checkpointer=checkpointer)

    async def _answer(self, state: ChatState) -> dict[str, object]:
        """One model call: an answer, or a request for tools with the changes among them to confirm."""
        messages = state.messages
        current = max((index for index, message in enumerate(messages) if isinstance(message, HumanMessage)), default=0)
        earlier = self._recent([message for message in messages[:current] if self._is_dialogue(message)])
        reply = await self._model.ainvoke([SystemMessage(self._system_prompt()), *earlier, *messages[current:]])
        changes = [call for call in reply.tool_calls if call["name"] in self.changing]
        return {"messages": [reply], "pending": [change for call in changes if (change := self._preview(call)) is not None]}

    @staticmethod
    def _next(state: ChatState) -> str:
        """confirm while changes wait for the user, tools for any other tool call, else the end."""
        if state.pending:
            return CONFIRM
        last = state.messages[-1] if state.messages else None
        return TOOLS if isinstance(last, AIMessage) and last.tool_calls else END

    @staticmethod
    async def _confirm(state: ChatState) -> Command[str]:
        """Wait for the user's answer to the pending changes, then run the tools or cancel the request."""
        answer = interrupt(state.pending)
        if answer is True:
            return Command(goto=TOOLS, update={"pending": []})
        request = state.messages[-1]
        calls = request.tool_calls if isinstance(request, AIMessage) else []
        # Answered in words too: later turns are sent only the questions and answers, not the tool results.
        cancelled: list[AnyMessage] = [
            *(ToolMessage(CANCELLED, tool_call_id=call["id"] or "", name=call["name"], status="error") for call in calls),
            AIMessage(NOT_DONE + "; ".join(state.pending)),
        ]
        if isinstance(answer, str):
            return Command(goto=AGENT, update={"pending": [], "messages": [*cancelled, HumanMessage(answer)]})
        return Command(goto=END, update={"pending": [], "messages": cancelled})

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

    @staticmethod
    def _is_read_only(tool: BaseTool) -> bool:
        """Whether the tool's server marked it read-only (a tool with no such mark may change things)."""
        return (tool.metadata or {}).get(READ_ONLY_HINT) is True
