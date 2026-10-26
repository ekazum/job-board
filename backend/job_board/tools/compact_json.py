"""The JSON the board's tools answer with."""

import json


def compact_json(value: dict[str, object]) -> str:
    """Compact JSON: every token counts in a small model's context."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
