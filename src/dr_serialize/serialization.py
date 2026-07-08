"""JSON-safe conversion engine with an ordered, pluggable handler chain.

A :class:`Serializer` bundles limits with a tuple of consumer handlers.
Consumer handlers run after the built-in scalar/container handlers and
before the fallback handlers (plain types, Pydantic models, generators,
``__dict__`` walks), so a consumer handler can intercept any
non-primitive value. Handlers recurse via
:meth:`ConversionContext.convert`, which owns depth and path bookkeeping.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pydantic

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.errors import (
    DEBUG_DETAIL_LIMIT,
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
from dr_serialize.limits import SerializationLimits

ENCODED_PREVIEW_SLICE = 8192

type JsonableHandle = tuple[bool, Any]
type JsonableHandler = Callable[[Any, ConversionContext], JsonableHandle]

_JSON_LEAF_TYPES = (type(None), bool, int, float, str)
_JSON_CONTAINER_TYPES = (*_JSON_LEAF_TYPES, dict, list)


@dataclass(frozen=True, slots=True)
class ConversionContext:
    """Per-node conversion state handed to handlers.

    ``path`` locates the current value for error construction.
    :meth:`convert` recurses into children; depth and path bookkeeping
    is owned by the library, not the handler.
    """

    serializer: Serializer
    depth: int
    path: JsonPath

    def convert(self, child: Any, key: str | int | None = None) -> Any:
        child_path = self.path if key is None else (*self.path, key)
        return _convert_node(
            self.serializer, child, self.depth + 1, child_path
        )


@dataclass(frozen=True, slots=True)
class Serializer:
    """JSON-safe converter: limits plus an ordered consumer-handler chain."""

    limits: SerializationLimits
    handlers: tuple[JsonableHandler, ...] = ()

    def to_jsonable(self, x: Any) -> Any:
        """Convert ``x`` to a JSON-safe value, enforcing ``self.limits``."""
        value = _convert_node(self, x, 0, ())
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except TypeError as error:
            failure_path, leaf = _find_non_jsonable_path(value)
            raise JsonEncodeError(
                path=failure_path,
                type_name=type(leaf).__name__,
                detail=detail_repr(leaf),
                underlying=error,
                value_preview=preview_repr(x),
            ) from error
        size_bytes = len(encoded.encode(TEXT_ENCODING))
        if size_bytes > self.limits.max_bytes:
            preview_head, preview_tail, detail = _encoded_preview_slices(
                encoded
            )
            raise PayloadTooLargeError(
                size_bytes=size_bytes,
                max_bytes=self.limits.max_bytes,
                postgres_max_bytes=self.limits.effective_hard_max_bytes,
                path=(),
                top_level_sizes=_top_level_key_sizes(value),
                preview_head=preview_head,
                preview_tail=preview_tail,
                detail=detail,
            )
        return value


def _convert_node(
    serializer: Serializer, x: Any, depth: int, path: JsonPath
) -> Any:
    if depth > serializer.limits.max_depth:
        raise MaxDepthExceededError(
            depth=depth,
            max_depth=serializer.limits.max_depth,
            path=path,
            value_preview=preview_repr(x),
            detail=detail_repr(x),
        )
    ctx = ConversionContext(serializer=serializer, depth=depth, path=path)
    for handler in (
        *_PRIMARY_HANDLERS,
        *serializer.handlers,
        *_FALLBACK_HANDLERS,
    ):
        handled, value = handler(x, ctx)
        if handled:
            return value
    return x


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


def _jsonable_scalar(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if x is None or isinstance(x, (bool, int, float, str)):
        return True, x
    return False, None


def _jsonable_sequence(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, (list, tuple, set, frozenset)):
        return True, [
            ctx.convert(item, index) for index, item in enumerate(x)
        ]
    return False, None


def _jsonable_mapping(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, dict):
        return True, {
            str(key): ctx.convert(item, str(key)) for key, item in x.items()
        }
    return False, None


def _jsonable_bytes(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if isinstance(x, bytes):
        return True, f"<bytes len={len(x)}>"
    return False, None


def _jsonable_type(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if not isinstance(x, type):
        return False, None
    return True, f"<class {x.__module__}.{x.__name__}>"


def _jsonable_pydantic_model(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    if isinstance(x, pydantic.BaseModel):
        try:
            dumped = x.model_dump(mode="json")
        except Exception as error:
            raise ModelDumpError(
                path=ctx.path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
        # Dumps are not guaranteed JSON-safe (custom field serializers can
        # emit arbitrary objects) and would otherwise bypass depth limits;
        # re-converting outside the try keeps SerializationErrors raised
        # during recursion from being relabeled as ModelDumpError.
        return True, _convert_node(ctx.serializer, dumped, ctx.depth, ctx.path)
    return False, None


def _jsonable_async_or_generator(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    del ctx
    if (
        inspect.iscoroutine(x)
        or inspect.isasyncgen(x)
        or inspect.isgenerator(x)
    ):
        return True, f"<{type(x).__name__}>"
    return False, None


def _jsonable_object_vars(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if hasattr(x, "__dict__") and not callable(x):
        try:
            return True, {
                key: ctx.convert(value, key)
                for key, value in vars(x).items()
            }
        except SerializationError:
            raise
        except Exception as error:
            raise ObjectVarsSerializationError(
                path=ctx.path,
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
