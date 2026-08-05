from __future__ import annotations

from typing import Any, cast

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
)
from dr_serialize._core.json_values import Jsonable, _find_strict_json_failure


class StrictJsonError(SerializationError):
    """A strict JSON validation failure.

    ``path`` identifies the first rejected value or key; no coercion is
    attempted.
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
    """Validate without coercion and return the original strict JSON value.

    Rejects non-string keys, non-finite numbers, reference cycles, and non-JSON
    runtime types; ``StrictJsonError.path`` identifies the first failure.
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
