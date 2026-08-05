from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from dr_serialize._core.json_values import _find_bounded_strict_json_failure

if TYPE_CHECKING:
    from dr_serialize._core.diagnostics import JsonPath
    from dr_serialize._core.json_values import _JsonFailure

CANONICAL_JSON_MAX_CONTAINER_DEPTH: Final[int] = 100
CANONICAL_JSON_MAX_INTEGER_DIGITS: Final[int] = 640


def _find_canonical_json_failure(
    value: Any,
    path: JsonPath = (),
) -> _JsonFailure | None:
    return _find_bounded_strict_json_failure(
        value,
        path,
        max_container_depth=CANONICAL_JSON_MAX_CONTAINER_DEPTH,
        max_integer_digits=CANONICAL_JSON_MAX_INTEGER_DIGITS,
    )


def _canonical_failure_detail(failure: _JsonFailure) -> str | None:
    if failure.reason == "maximum container depth":
        return (
            f"container depth {failure.actual} exceeds maximum "
            f"{failure.maximum}"
        )
    if failure.reason == "maximum integer digits":
        return f"integer exceeds maximum {failure.maximum} decimal digits"
    return None
