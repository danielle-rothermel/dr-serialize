"""The JSON-safe boundary type between dr-serialize's lanes.

The conversion engine (:class:`~dr_serialize.serialization.Serializer`)
produces ``Jsonable``; the canonical JSON utilities
(:func:`~dr_serialize.canonical.canonical_json`,
:func:`~dr_serialize.canonical.json_hash`) and the identity lane
(:mod:`dr_serialize.identity`) consume it.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dr_serialize.errors import JsonPath

type Jsonable = (
    None | bool | int | float | str | list[Jsonable] | dict[str, Jsonable]
)

JSON_LEAF_TYPES = (type(None), bool, int, float, str)


def find_json_failure(
    value: Any,
    path: JsonPath = (),
    *,
    reject_non_finite: bool = False,
) -> tuple[JsonPath, Any] | None:
    """Locate the first leaf ``json.dumps`` would reject, or ``None``."""
    return _find_json_failure(
        value,
        path,
        frozenset(),
        reject_non_finite=reject_non_finite,
    )


def _find_json_failure(  # noqa: PLR0911 -- exhaustive JSON leaf walk
    value: Any,
    path: JsonPath,
    seen: frozenset[int],
    *,
    reject_non_finite: bool,
) -> tuple[JsonPath, Any] | None:
    """Recursive walk carrying ``id()``-based cycle-detection state.

    ``seen`` holds the ``id()`` of every container on the current path;
    revisiting one is a reference cycle and is reported as a failure at
    ``path`` rather than recursing forever.
    """
    if reject_non_finite and isinstance(value, float) and not math.isfinite(
        value
    ):
        return path, value
    if isinstance(value, JSON_LEAF_TYPES):
        return None
    if isinstance(value, dict):
        if id(value) in seen:
            return path, value
        inner = seen | {id(value)}
        for key, item in value.items():
            if not isinstance(key, str):
                return path, key
            found = _find_json_failure(
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
            return path, value
        inner = seen | {id(value)}
        for index, item in enumerate(value):
            found = _find_json_failure(
                item,
                (*path, index),
                inner,
                reject_non_finite=reject_non_finite,
            )
            if found is not None:
                return found
        return None
    return path, value
