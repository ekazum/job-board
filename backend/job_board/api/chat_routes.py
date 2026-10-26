"""HTTP endpoints under /api/chat."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import StreamingResponse

from job_board.chat.chat_agent import ChatAgent
from job_board.chat.chat_event import ChatEvent
from job_board.models.chat_history import ChatHistory
from job_board.models.chat_request import THREAD_ID, ChatRequest
from job_board.models.chat_resume import ChatResume
from job_board.tools.board_tools import MOUNT_PATH

ThreadId = Annotated[str, Path(pattern=THREAD_ID)]
EVENT_STREAM = "text/event-stream"
STREAM_RESPONSE: dict[int | str, dict[str, object]] = {
    status.HTTP_200_OK: {"content": {EVENT_STREAM: {}}, "description": "The answer as server-sent events"}
}
LOOPBACK = "127.0.0.1"
ANY_HOST = frozenset({"0.0.0.0", "::"})  # a server listening on every interface is reached on the loopback one


class ChatRoutes:
    """Send a message (the answer streams back as server-sent events: thread, token, tool, tool_result, then confirm
    when it waits for the user to confirm changes to the board, then done or error), answer a confirm (resume), read a
    conversation, forget one."""

    def __init__(self, agent: ChatAgent) -> None:
        self._agent = agent

    def router(self) -> APIRouter:
        """Build the APIRouter with this instance's endpoints."""
        router = APIRouter(prefix="/api/chat", tags=["chat"])
        router.add_api_route("", self.chat, methods=["POST"], response_class=StreamingResponse, responses=STREAM_RESPONSE)
        router.add_api_route(
            "/{thread_id}/resume",
            self.resume_chat,
            methods=["POST"],
            response_class=StreamingResponse,
            responses={
                **STREAM_RESPONSE,
                status.HTTP_409_CONFLICT: {"description": "Nothing in this conversation waits for a confirm"},
            },
        )
        router.add_api_route(
            "/{thread_id}",
            self.chat_history,
            methods=["GET"],
            responses={status.HTTP_404_NOT_FOUND: {"description": "No conversation with this id"}},
        )
        router.add_api_route("/{thread_id}", self.delete_chat, methods=["DELETE"], status_code=status.HTTP_204_NO_CONTENT)
        return router

    async def chat(self, body: ChatRequest, request: Request) -> StreamingResponse:
        """Answer a message; a new conversation gets its id in the first (thread) event."""
        thread_id = body.thread_id or uuid4().hex
        return self._streamed(self._agent.stream(thread_id, body.message, self._mcp_url(request)))

    async def resume_chat(self, thread_id: ThreadId, body: ChatResume, request: Request) -> StreamingResponse:
        """Answer the confirm the conversation waits on: approve makes the changes, false cancels them."""
        if not await self._agent.pending(thread_id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"nothing in conversation {thread_id} waits for a confirm")
        return self._streamed(self._agent.resume(thread_id, body.approve, self._mcp_url(request)))

    async def chat_history(self, thread_id: ThreadId) -> ChatHistory:
        """A conversation so far."""
        lines = await self._agent.history(thread_id)
        if lines is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"conversation {thread_id} not found")
        return ChatHistory(thread_id=thread_id, lines=lines, pending=await self._agent.pending(thread_id))

    async def delete_chat(self, thread_id: ThreadId) -> None:
        """Forget a conversation (New chat)."""
        await self._agent.delete(thread_id)

    @staticmethod
    def _mcp_url(request: Request) -> str:
        """The board's MCP endpoint on the socket this server listens on (not through a proxy such as Vite's)."""
        base = request.base_url
        host, port = request.scope.get("server") or (None, None)  # ASGI: (host, port) of the listening socket
        if isinstance(host, str) and isinstance(port, int):
            base = base.replace(hostname=LOOPBACK if host in ANY_HOST else host, port=port)
        return f"{str(base).rstrip('/')}{MOUNT_PATH}/"

    @staticmethod
    def _streamed(events: AsyncIterator[ChatEvent]) -> StreamingResponse:
        """The events as a server-sent event stream, sent as they come."""
        return StreamingResponse(
            ChatRoutes._server_sent(events), media_type=EVENT_STREAM, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @staticmethod
    async def _server_sent(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
        """Each event as "event: <kind>" and "data: <json>"."""
        async for event in events:
            yield f"event: {event.kind}\ndata: {json.dumps(event.data, ensure_ascii=False, default=str)}\n\n"
