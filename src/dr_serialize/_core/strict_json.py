"""Validation at the finite strict JSON value boundary."""

from __future__ import annotations

from typing import Any, cast

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
)
from dr_serialize._core.json_values import Jsonable, _find_strict_json_failure


class StrictJsonError(SerializationError):
    """A value is not a strict JSON value.

    Raised by :func:`validate_strict_json` (and therefore by document
    validation and hashing) when a value is not JSON, has a non-string
    object key, is a non-finite number, or forms a reference cycle. The
    ``path`` locates the exact offending leaf or key JsonPath-style.
    """

    def __init__(
        self,
        *,
        path: JsonPath,
        reason: str,
        type_name: str,
        detail: str,
    ) -> None:
        self.path = path
        self.reason = reason
        self.type_name = type_name
        self.detail = detail
        super().__init__(
            "not a strict JSON value at path "
            f"{detail_repr(path)}: {reason} ({type_name})"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "reason": self.reason,
            "type_name": self.type_name,
        }


def validate_strict_json(value: Any) -> Jsonable:
    """Return ``value`` if it is a strict JSON value, else raise.

    Accepts, recursively: ``None``, ``bool``, ``int``, finite ``float``,
    ``str``, ``list`` of accepted values, and ``dict`` with ``str`` keys and
    accepted values. Rejects every other runtime type, non-string dict keys,
    non-finite numbers (``NaN``/``Inf``), and reference cycles, raising
    :class:`StrictJsonError` with the JsonPath-style ``path`` to the first
    offending value or key. No coercion or normalization is performed.
    """
    return _validate_strict_json(value, ())


def _validate_strict_json(value: Any, path: JsonPath) -> Jsonable:
    failure = _find_strict_json_failure(value, path)
    if failure is None:
        return cast("Jsonable", value)
    raise StrictJsonError(
        path=failure.path,
        reason=failure.reason,
        type_name=type(failure.leaf).__name__,
        detail=detail_repr(failure.leaf),
    )
