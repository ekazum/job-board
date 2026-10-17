"""Narrow untyped JSON and YAML values (json.loads / yaml.safe_load return Any) to concrete types."""

from typing import TypeGuard


def is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    """isinstance(value, dict), with the key and value types spelled out for the type checkers."""
    return isinstance(value, dict)


def is_object_list(value: object) -> TypeGuard[list[object]]:
    """isinstance(value, list), with the item type spelled out for the type checkers."""
    return isinstance(value, list)


def as_dict(value: object) -> dict[str, object] | None:
    """The value as a mapping with string keys (non-string keys are dropped), or None if it is not a mapping."""
    if is_object_dict(value):
        return {key: item for key, item in value.items() if isinstance(key, str)}
    return None


def as_list(value: object) -> list[object] | None:
    """The value as a list, or None if it is not one."""
    if is_object_list(value):
        return value
    return None


def dicts(value: object) -> list[dict[str, object]]:
    """The mappings inside a list; anything that is not a list of mappings yields []."""
    items = as_list(value) or []
    return [item for item in (as_dict(element) for element in items) if item is not None]


def as_str(value: object) -> str:
    """A string, or "" for anything else (null, missing, numbers)."""
    return value if isinstance(value, str) else ""


def as_id(value: object) -> str:
    """A string or integer id as str; "" when absent. Booleans are rejected (bool is an int subclass)."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int | str):
        return str(value)
    return ""
