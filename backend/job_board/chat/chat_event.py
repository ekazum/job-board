"""Value object for one step of a streamed chat answer."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatEvent:
    """kind is thread ({thread_id}), token ({text}: more of the answer), tool ({name, args}: the model asked for a
    tool), tool_result ({name, summary, changed}: changed when the tool changed the board), confirm ({changes}: the
    answer waits for the user to confirm these, in words), done ({}) or error ({message}); data is sent as the event's
    JSON."""

    kind: str
    data: dict[str, object] = field(default_factory=dict[str, object])
