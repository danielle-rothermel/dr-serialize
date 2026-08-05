"""The JSON-safe boundary type between dr-serialize's lanes.

The conversion engine (:class:`~dr_serialize.serialization.Serializer`)
produces ``Jsonable``; the Canonical JSON Text utilities
(:func:`~dr_serialize.canonical.canonical_json`,
:func:`~dr_serialize.canonical.json_hash`) and the identity lane
(:mod:`dr_serialize.identity`) consume it.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from dr_serialize.errors import JsonPath

type Jsonable = (
    None | bool | int | float | str | list[Jsonable] | dict[str, Jsonable]
)

JSON_LEAF_TYPES = (type(None), bool, int, float, str)

type _JsonFailureReason = Literal[
    "non-finite number",
    "non-string object key",
    "reference cycle",
    "unsupported type",
]
type _JsonFailure = tuple[JsonPath, Any, _JsonFailureReason]


def find_json_failure(
    value: Any,
    path: JsonPath = (),
    *,
    reject_non_finite: bool = False,
) -> tuple[JsonPath, Any] | None:
    """Locate the first leaf ``json.dumps`` would reject, or ``None``."""
    failure = _walk_json_failure(
        value,
        path,
        frozenset(),
        reject_non_finite=reject_non_finite,
    )
    if failure is None:
        return None
    failure_path, leaf, _reason = failure
    return failure_path, leaf


def _find_strict_json_failure(
    value: Any,
    path: JsonPath = (),
) -> _JsonFailure | None:
    """Locate the first value outside the strict JSON data model."""
    return _walk_json_failure(
        value,
        path,
        frozenset(),
        reject_non_finite=True,
    )


def _walk_json_failure(  # noqa: PLR0911 -- exhaustive JSON leaf walk
    value: Any,
    path: JsonPath,
    seen: frozenset[int],
    *,
    reject_non_finite: bool,
) -> _JsonFailure | None:
    """Recursive walk carrying ``id()``-based cycle-detection state.

    ``seen`` holds the ``id()`` of every container on the current path;
    revisiting one is a reference cycle and is reported as a failure at
    ``path`` rather than recursing forever.
    """
    if (
        reject_non_finite
        and isinstance(value, float)
        and not math.isfinite(value)
    ):
        return path, value, "non-finite number"
    if isinstance(value, JSON_LEAF_TYPES):
        return None
    if isinstance(value, dict):
        if id(value) in seen:
            return path, value, "reference cycle"
        inner = seen | {id(value)}
        for key, item in value.items():
            if not isinstance(key, str):
                return path, key, "non-string object key"
            found = _walk_json_failure(
                item,
                (*path, key),
                inner,
                reject_non_finite=reject_non_finite,
            )
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        if id(value) in seen:
            return path, value, "reference cycle"
        inner = seen | {id(value)}
        for index, item in enumerate(value):
            found = _walk_json_failure(
                item,
                (*path, index),
                inner,
                reject_non_finite=reject_non_finite,
            )
            if found is not None:
                return found
        return None
    return path, value, "unsupported type"
