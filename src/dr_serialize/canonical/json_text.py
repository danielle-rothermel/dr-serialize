"""The frozen dr-serialize Canonical JSON Text profile v1."""

from __future__ import annotations

import json

from dr_serialize._core.diagnostics import detail_repr, preview_repr
from dr_serialize._core.encoding import TEXT_ENCODING
from dr_serialize._core.json_values import (
    Jsonable,
    _find_strict_json_failure,
)
from dr_serialize.canonical.errors import JsonEncodeError


def canonical_json(value: Jsonable) -> str:
    """Render ``value`` using dr-serialize Canonical JSON Text profile v1.

    Runtime validation rejects values outside strict ``Jsonable`` before
    encoding. Unsupported types, non-string object keys, and reference cycles
    carry an underlying :class:`TypeError`; non-finite numbers carry an
    underlying :class:`ValueError`.
    """
    failure = _find_strict_json_failure(value)
    if failure is not None:
        failure_path, leaf, reason = failure
        underlying: TypeError | ValueError
        if reason == "non-finite number":
            underlying = ValueError(reason)
        else:
            underlying = TypeError(reason)
        error = JsonEncodeError(
            path=failure_path,
            type_name=type(leaf).__name__,
            detail=detail_repr(leaf),
            underlying=underlying,
            value_preview=preview_repr(value),
        )
        raise error from underlying

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise JsonEncodeError(
            path=(),
            type_name=type(value).__name__,
            detail=detail_repr(value),
            underlying=error,
            value_preview=preview_repr(value),
        ) from error


def canonical_json_bytes(value: Jsonable, /) -> bytes:
    """Return the exact UTF-8 bytes of :func:`canonical_json`."""
    return canonical_json(value).encode(TEXT_ENCODING)
