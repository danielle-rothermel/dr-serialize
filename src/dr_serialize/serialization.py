"""JSON-safe conversion engine with an ordered, pluggable handler chain.

The library ships stdlib + Pydantic handlers only. Consumers register
their own handlers with :func:`register_handler`; registered handlers run
after the built-in scalar/container handlers and before the fallback
handlers (plain types, Pydantic models, generators, ``__dict__`` walks),
so a consumer handler can intercept any non-primitive value.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

import pydantic

from dr_serialize.errors import (
    JsonEncodeError,
    JsonPath,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationError,
    detail_repr,
    preview_repr,
)
from dr_serialize.limits import DEFAULT_MAX_DEPTH, SerializationLimits

ENCODED_PREVIEW_SLICE = 8192
DEBUG_DETAIL_LIMIT = 256 * 1024
TEXT_ENCODING = "utf-8"

type JsonableHandle = tuple[bool, Any]
type JsonableHandler = Callable[[Any, int, JsonPath], JsonableHandle]

_JSON_LEAF_TYPES = (type(None), bool, int, float, str)
_JSON_CONTAINER_TYPES = (*_JSON_LEAF_TYPES, dict, list)

_ACTIVE_MAX_DEPTH: ContextVar[int] = ContextVar(
    "dr_serialize_active_max_depth",
    default=DEFAULT_MAX_DEPTH,
)


def _encoded_preview_slices(encoded: str) -> tuple[str, str, str]:
    head = encoded[:ENCODED_PREVIEW_SLICE]
    if len(encoded) > ENCODED_PREVIEW_SLICE:
        tail = encoded[-ENCODED_PREVIEW_SLICE:]
    else:
        tail = ""
    detail = f"head:\n{head}"
    if tail:
        detail = f"{detail}\n\ntail:\n{tail}"
    if len(detail) > DEBUG_DETAIL_LIMIT:
        detail = detail[:DEBUG_DETAIL_LIMIT]
    return head, tail, detail


def _top_level_key_sizes(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): len(json.dumps(item, ensure_ascii=False).encode())
        for key, item in value.items()
    }


def _find_non_jsonable_path(  # noqa: PLR0911 -- exhaustive leaf walk
    value: Any,
    path: JsonPath = (),
) -> tuple[JsonPath, Any]:
    if isinstance(value, _JSON_LEAF_TYPES):
        return path, value
    if isinstance(value, dict):
        for key, item in value.items():
            sub_path = (*path, str(key))
            if not isinstance(item, _JSON_CONTAINER_TYPES):
                return sub_path, item
            found_path, leaf = _find_non_jsonable_path(item, sub_path)
            if not isinstance(leaf, _JSON_LEAF_TYPES):
                return found_path, leaf
        return path, value
    if isinstance(value, list):
        for index, item in enumerate(value):
            sub_path = (*path, index)
            if not isinstance(item, _JSON_CONTAINER_TYPES):
                return sub_path, item
            found_path, leaf = _find_non_jsonable_path(item, sub_path)
            if not isinstance(leaf, _JSON_LEAF_TYPES):
                return found_path, leaf
        return path, value
    return path, value


def _check_max_depth(x: Any, depth: int, path: JsonPath) -> None:
    max_depth = _ACTIVE_MAX_DEPTH.get()
    if depth > max_depth:
        raise MaxDepthExceededError(
            depth=depth,
            max_depth=max_depth,
            path=path,
            value_preview=preview_repr(x),
            detail=detail_repr(x),
        )


def _jsonable_scalar(x: Any, depth: int, path: JsonPath) -> JsonableHandle:
    del depth, path
    if x is None or isinstance(x, (bool, int, float, str)):
        return True, x
    return False, None


def _jsonable_sequence(x: Any, depth: int, path: JsonPath) -> JsonableHandle:
    if isinstance(x, (list, tuple, set, frozenset)):
        return True, [
            convert_value(item, depth + 1, (*path, index))
            for index, item in enumerate(x)
        ]
    return False, None


def _jsonable_mapping(x: Any, depth: int, path: JsonPath) -> JsonableHandle:
    if isinstance(x, dict):
        return True, {
            str(key): convert_value(item, depth + 1, (*path, str(key)))
            for key, item in x.items()
        }
    return False, None


def _jsonable_bytes(x: Any, depth: int, path: JsonPath) -> JsonableHandle:
    del depth, path
    if isinstance(x, bytes):
        return True, f"<bytes len={len(x)}>"
    return False, None


def _jsonable_type(x: Any, depth: int, path: JsonPath) -> JsonableHandle:
    del depth, path
    if not isinstance(x, type):
        return False, None
    return True, f"<class {x.__module__}.{x.__name__}>"


def _jsonable_pydantic_model(
    x: Any, depth: int, path: JsonPath
) -> JsonableHandle:
    del depth
    if isinstance(x, pydantic.BaseModel):
        try:
            return True, x.model_dump(mode="json")
        except Exception as error:
            raise ModelDumpError(
                path=path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
    return False, None


def _jsonable_async_or_generator(
    x: Any, depth: int, path: JsonPath
) -> JsonableHandle:
    del depth, path
    if (
        inspect.iscoroutine(x)
        or inspect.isasyncgen(x)
        or inspect.isgenerator(x)
    ):
        return True, f"<{type(x).__name__}>"
    return False, None


def _jsonable_object_vars(
    x: Any, depth: int, path: JsonPath
) -> JsonableHandle:
    if hasattr(x, "__dict__") and not callable(x):
        try:
            return True, {
                key: convert_value(value, depth + 1, (*path, key))
                for key, value in vars(x).items()
            }
        except SerializationError:
            raise
        except Exception as error:
            raise ObjectVarsSerializationError(
                path=path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
    return False, None


_PRIMARY_HANDLERS: tuple[JsonableHandler, ...] = (
    _jsonable_scalar,
    _jsonable_sequence,
    _jsonable_mapping,
    _jsonable_bytes,
)

_FALLBACK_HANDLERS: tuple[JsonableHandler, ...] = (
    _jsonable_type,
    _jsonable_pydantic_model,
    _jsonable_async_or_generator,
    _jsonable_object_vars,
)

_registered_handlers: list[JsonableHandler] = []


def register_handler(handler: JsonableHandler) -> None:
    """Add a consumer handler to the conversion chain.

    Registered handlers run in registration order, after the built-in
    scalar/container handlers and before the fallback handlers.
    Registering the same handler twice is a no-op.
    """
    if handler not in _registered_handlers:
        _registered_handlers.append(handler)


def registered_handlers() -> tuple[JsonableHandler, ...]:
    return tuple(_registered_handlers)


def clear_registered_handlers() -> None:
    _registered_handlers.clear()


def convert_value(x: Any, depth: int = 0, path: JsonPath = ()) -> Any:
    """Recursive, depth-bounded conversion entry point.

    Consumer handlers call this to convert nested values; the active
    depth limit is carried from the enclosing ``to_jsonable`` /
    ``to_metadata_dict`` call.
    """
    _check_max_depth(x, depth, path)
    for handler in (
        *_PRIMARY_HANDLERS,
        *_registered_handlers,
        *_FALLBACK_HANDLERS,
    ):
        handled, value = handler(x, depth, path)
        if handled:
            return value
    return x


def to_metadata_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion to a metadata dict.

    Skips persistence size limits; only the default depth guard applies.
    """
    try:
        converted = convert_value(value)
    except SerializationError:
        if isinstance(value, dict):
            return dict(value)
        return {}
    if isinstance(converted, dict):
        return converted
    return {"response": converted}


def to_jsonable(x: Any, *, limits: SerializationLimits) -> Any:
    """Convert ``x`` to a JSON-safe value, enforcing the given limits."""
    depth_token = _ACTIVE_MAX_DEPTH.set(limits.max_depth)
    try:
        value = convert_value(x)
    finally:
        _ACTIVE_MAX_DEPTH.reset(depth_token)
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except TypeError as error:
        failure_path, leaf = _find_non_jsonable_path(value)
        type_name = type(leaf).__name__
        raise JsonEncodeError(
            path=failure_path,
            type_name=type_name,
            detail=detail_repr(leaf),
            underlying=error,
            value_preview=preview_repr(x),
        ) from error
    size_bytes = len(encoded.encode(TEXT_ENCODING))
    if size_bytes > limits.max_bytes:
        preview_head, preview_tail, detail = _encoded_preview_slices(encoded)
        raise PayloadTooLargeError(
            size_bytes=size_bytes,
            max_bytes=limits.max_bytes,
            postgres_max_bytes=limits.effective_hard_max_bytes,
            path=(),
            top_level_sizes=_top_level_key_sizes(value),
            preview_head=preview_head,
            preview_tail=preview_tail,
            detail=detail,
        )
    return value
