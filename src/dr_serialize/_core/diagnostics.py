"""Shared error base, paths, and bounded diagnostic rendering."""

from __future__ import annotations

from typing import Any

MESSAGE_PREVIEW = 512
DEBUG_DETAIL_LIMIT = 256 * 1024

type JsonPath = tuple[str | int, ...]


def _bounded_repr(x: Any, limit: int) -> str:
    try:
        rendered = repr(x)
    except Exception as error:  # noqa: BLE001 -- diagnostics must not escape
        rendered = (
            f"<repr failed for {type(x).__name__}: {type(error).__name__}>"
        )
    # repr may legally return a str subclass with an overridden __getitem__.
    return str.__getitem__(rendered, slice(limit))


def preview_repr(x: Any) -> str:
    return _bounded_repr(x, MESSAGE_PREVIEW)


def detail_repr(x: Any) -> str:
    return _bounded_repr(x, DEBUG_DETAIL_LIMIT)


class SerializationError(Exception):
    """Base for JSON-safe serialization failures."""

    path: JsonPath
    detail: str

    def diagnostics(self) -> dict[str, Any]:
        raise NotImplementedError
