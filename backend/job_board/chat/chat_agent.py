"""Answer chat messages with the LangGraph agent, and keep the conversations."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, TypeIs

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from job_board.chat.chat_event import ChatEvent
from job_board.chat.chat_graph import AGENT, CANCELLED, CONFIRM, TOOLS, ChatGraph, Preview
from job_board.chat.chat_state import ChatState
from job_board.chat.chat_model_factory import ChatModelFactory
from job_board.config.chat_settings import ChatSettings
from job_board.models.chat_line import ChatLine
from job_board.models.profile import Profile
from job_board.utils.json_values import as_dict, as_list
from job_board.utils.prompt_files import prompt

logger = logging.getLogger(__name__)

ToolsLoader = Callable[[str], Awaitable[list[BaseTool]]]
MCP_SERVER = "job-board"
TARGETS_CHARS = 800


class ChatAgent:
    """Answers one message at a time per conversation, streaming ChatEvents: the thread id, the answer's text as the
    model writes it, each tool it calls and what came back, the changes to confirm when it asks to change the board,
    then done or error. resume() goes on from a confirm; a message sent instead cancels the changes waiting for one.

    Conversations are saved by LangGraph's SQLite checkpointer in db_path (chat.db beside the board's database), one
    thread each, so they survive a reload or a restart. For every message the model and the chat settings are read
    from config.yaml again, the tools are listed by the board's MCP server at mcp_url, and the system prompt
    (prompts/chat_system.txt) gets today's date and the profile's location, job titles and targets.
    """

    def __init__(
        self,
        db_path: Path,
        model_factory: ChatModelFactory,
        settings_loader: Callable[[], ChatSettings],
        profile_loader: Callable[[], Profile | None],
        preview: Preview,
        tools_loader: ToolsLoader | None = None,
    ) -> None:
        self._db_path = db_path
        self._model_factory = model_factory
        self._settings_loader = settings_loader
        self._profile_loader = profile_loader
        self._preview = preview
        self._tools_loader = tools_loader or self._mcp_tools
        self._saver: AsyncSqliteSaver | None = None

    @asynccontextmanager
    async def opened(self) -> AsyncGenerator[None]:
        """Keep the conversation store open while the app runs."""
        async with AsyncSqliteSaver.from_conn_string(str(self._db_path)) as saver:
            self._saver = saver
            try:
                yield
            finally:
                self._saver = None

    async def stream(self, thread_id: str, message: str, mcp_url: str) -> AsyncIterator[ChatEvent]:
        """The answer to message in conversation thread_id, as it is written."""
        yield ChatEvent("thread", {"thread_id": thread_id})
        async for event in self._events(thread_id, mcp_url, message):
            yield event

    async def resume(self, thread_id: str, approve: bool, mcp_url: str) -> AsyncIterator[ChatEvent]:
        """The rest of the answer once the user confirmed (approve) or cancelled the changes it waits on."""
        async for event in self._events(thread_id, mcp_url, approve):
            yield event

    async def pending(self, thread_id: str) -> list[str]:
        """The changes waiting for the user's confirm in a conversation, in words; [] when none."""
        found = await self._open_saver().aget_tuple(self._config(thread_id))
        values = [] if found is None else as_list(found.checkpoint["channel_values"].get("pending")) or []
        return [value for value in values if isinstance(value, str)]

    async def _events(self, thread_id: str, mcp_url: str, turn: str | bool) -> AsyncIterator[ChatEvent]:
        """The graph's events on a message or a confirm's answer. The graph runs as a task, so whatever stops it (the
        model unreachable, the step limit) ends the stream with an error event; leaving early (the user pressed Stop)
        cancels it."""
        events: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(thread_id, mcp_url, turn, events))
        task.add_done_callback(lambda _: events.put_nowait(None))
        try:
            while (event := await events.get()) is not None:
                yield event
        finally:
            task.cancel()
        yield self._outcome(task)

    async def history(self, thread_id: str) -> list[ChatLine] | None:
        """The conversation so far (questions, answers and the tools used); None when there is no such thread."""
        found = await self._open_saver().aget_tuple(self._config(thread_id))
        if found is None:
            return None
        messages = as_list(found.checkpoint["channel_values"].get("messages")) or []
        return [line for message in messages for line in self._lines(message)]

    async def delete(self, thread_id: str) -> None:
        """Forget a conversation."""
        await self._open_saver().adelete_thread(thread_id)

    async def _run(self, thread_id: str, mcp_url: str, turn: str | bool, events: asyncio.Queue[ChatEvent | None]) -> None:
        """Run the graph on a message or a confirm's answer, queueing its events. A message sent while changes wait
        for a confirm is that confirm's answer too: it cancels them."""
        settings = self._settings_loader()
        tools = await self._tools_loader(mcp_url)
        chat_graph = ChatGraph(self._model_factory.create(), tools, self._system_prompt, settings.history_tokens, self._preview)
        graph = chat_graph.compile(self._open_saver())
        config: RunnableConfig = {**self._config(thread_id), "recursion_limit": settings.max_steps}
        if isinstance(turn, bool) or await self.pending(thread_id):
            run_input: ChatState | Command[str] = Command(resume=turn)
        else:
            run_input = ChatState(messages=[HumanMessage(turn)])
        async for part in graph.astream(run_input, config, stream_mode=["messages", "updates"], version="v2"):
            if part["type"] == "messages":
                found = self._token(*part["data"])
            elif part["type"] == "updates":
                found = [
                    event
                    for node, update in part["data"].items()
                    for event in self._step_events(node, update, chat_graph.changing)
                ]
            else:
                found = []
            for event in found:
                events.put_nowait(event)
        if changes := await self.pending(thread_id):
            events.put_nowait(ChatEvent("confirm", {"changes": changes}))

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        """The checkpointer's key for a conversation."""
        return {"configurable": {"thread_id": thread_id}}

    def _open_saver(self) -> AsyncSqliteSaver:
        """The conversation store; RuntimeError outside the app's lifetime."""
        if self._saver is None:
            raise RuntimeError("the chat store is not open")
        return self._saver

    def _system_prompt(self) -> str:
        """The system prompt with today's date and the profile."""
        return prompt("chat_system.txt").format(today=date.today().isoformat(), profile=self._profile_text(self._profile_loader()))

    @staticmethod
    def _profile_text(profile: Profile | None) -> str:
        """The profile in a few lines (the CV is left to the get_profile tool)."""
        if profile is None:
            return "No profile has been saved yet."
        remote = ", fully remote jobs welcome" if profile.allow_fully_remote else ""
        lines = [f"Location: {profile.location or 'not set'}{remote}", profile.job_titles()]
        if profile.targets.strip():
            lines.append(f"Looking for: {profile.targets.strip()[:TARGETS_CHARS]}")
        return "\n".join(lines)

    @staticmethod
    def _token(message: AnyMessage, metadata: dict[str, Any]) -> list[ChatEvent]:
        """More of the answer, from a piece of the agent's reply as the model writes it."""
        if isinstance(message, AIMessageChunk) and metadata.get("langgraph_node") == AGENT and message.text:
            return [ChatEvent("token", {"text": message.text})]
        return []

    def _step_events(self, node: str, update: object, changing: frozenset[str]) -> list[ChatEvent]:
        """A tool event per tool the agent asked for, a tool_result event per result, a cancelled call's included
        (changed: a tool that changes the board did)."""
        messages = as_list((as_dict(update) or {}).get("messages")) or []
        events: list[ChatEvent] = []
        for message in messages:
            if node == AGENT and isinstance(message, AIMessage):
                events.extend(ChatEvent("tool", {"name": call["name"], "args": call["args"]}) for call in message.tool_calls)
            elif node in (TOOLS, CONFIRM) and isinstance(message, ToolMessage):
                changed = node == TOOLS and message.name in changing and message.status != "error"
                events.append(
                    ChatEvent("tool_result", {"name": message.name, "summary": self._summary(message), "changed": changed})
                )
        return events

    def _lines(self, message: object) -> list[ChatLine]:
        """A saved message as the chat window shows it; tool requests and empty answers are left out."""
        if isinstance(message, HumanMessage):
            return [ChatLine(role="user", text=message.text)]
        if isinstance(message, AIMessage) and message.text:
            return [ChatLine(role="assistant", text=message.text)]
        if isinstance(message, ToolMessage):
            return [ChatLine(role="tool", text=f"{message.name} · {self._summary(message)}")]
        return []

    @staticmethod
    def _summary(message: ToolMessage) -> str:
        """"12 found" for a search, "cancelled" when the user said no, "failed" for an error, "done" otherwise."""
        if message.text == CANCELLED:
            return "cancelled"
        if message.status == "error":
            return "failed"
        try:
            count = (as_dict(json.loads(message.text)) or {}).get("count")
        except json.JSONDecodeError:
            return "done"
        return f"{count} found" if isinstance(count, int) else "done"

    @staticmethod
    def _outcome(task: asyncio.Task[None]) -> ChatEvent:
        """done, or error with the reason the answer stopped."""
        if task.cancelled():
            return ChatEvent("error", {"message": "stopped"})
        failure = task.exception()
        if failure is None:
            return ChatEvent("done")
        error = ChatAgent._cause(failure)
        if isinstance(error, GraphRecursionError):
            message = "stopped after too many steps; try a narrower question"
        else:
            message = f"{type(error).__name__}: {error}"
        logger.error("chat answer stopped: %s", message, exc_info=error)
        return ChatEvent("error", {"message": message})

    @staticmethod
    def _cause(error: BaseException) -> BaseException:
        """The one failure an exception group wraps (the MCP client's task groups do), else the error itself."""
        while ChatAgent._is_group(error):
            if len(error.exceptions) != 1:
                return error
            error = error.exceptions[0]
        return error

    @staticmethod
    def _is_group(error: BaseException) -> TypeIs[BaseExceptionGroup[BaseException]]:
        """Whether error is an exception group (whose members are exceptions)."""
        return isinstance(error, BaseExceptionGroup)

    @staticmethod
    async def _mcp_tools(url: str) -> list[BaseTool]:
        """The tools the board's MCP server lists."""
        return await MultiServerMCPClient({MCP_SERVER: {"transport": "streamable_http", "url": url}}).get_tools()
