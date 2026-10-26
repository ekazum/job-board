"""What a board change the chat agent asks for will do, in words, for the confirm card."""

import json
from collections.abc import Callable

from langchain_core.messages import ToolCall

from job_board.models.posting import Posting
from job_board.tools.board_actions import ADD_NOTE, CLOSE_POSTING, MOVE_POSTING, START_SCAN
from job_board.utils.json_values import as_str


class ChangePreview:
    """"Move #42 “Backend Engineer” at Acme from New to Applied" and the like. A call naming a posting that does not
    exist gets None (the tool can only fail, so there is nothing to confirm); a call this does not know is shown as it
    is, so it is still confirmed."""

    def __init__(self, posting_loader: Callable[[int], Posting | None]) -> None:
        self._posting_loader = posting_loader

    def describe(self, call: ToolCall) -> str | None:
        """The change the call will make."""
        name, args = call["name"], call["args"]
        if name == START_SCAN:
            return "Start a scan: read every company's job board and add the matching new jobs to New"
        posting_id = self._posting_id(args.get("posting_id"))
        posting = None if posting_id is None else self._posting_loader(posting_id)
        if posting_id is not None and posting is None:
            return None
        if posting is not None:
            subject = f"#{posting.id} “{posting.title}” at {posting.company}"
            if name == MOVE_POSTING:
                return f"Move {subject} from {self._words(posting.status)} to {self._words(args.get('status'))}"
            if name == CLOSE_POSTING:
                now = self._words(posting.status)
                return f"Close {subject} (now in {now}), outcome: {self._words(args.get('outcome')).lower()}"
            if name == ADD_NOTE:
                return f"Add to the note on {subject}: “{as_str(args.get('text'))}”"
        return f"{name} {json.dumps(args, ensure_ascii=False)}"

    @staticmethod
    def _posting_id(value: object) -> int | None:
        """The id as the tool will read it (a whole number, maybe written as text), or None when there is none."""
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _words(value: object) -> str:
        """A column or an outcome as the board shows it: applied -> Applied, not_relevant -> Not relevant."""
        return as_str(value).replace("_", " ").capitalize()
