"""The boundary type between dr-serialize's two lanes.

The conversion engine (:class:`~dr_serialize.serialization.Serializer`)
produces ``Jsonable``; the identity lane
(:func:`~dr_serialize.canonical.canonical_json`,
:func:`~dr_serialize.canonical.json_hash`) consumes it.
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


def find_json_failure(  # noqa: PLR0911 -- exhaustive JSON leaf walk
    value: Any,
    path: JsonPath = (),
    *,
    reject_non_finite: bool = False,
) -> tuple[JsonPath, Any] | None:
    """Locate the first leaf ``json.dumps`` would reject, or ``None``."""
    if reject_non_finite and isinstance(value, float) and not math.isfinite(
        value
    ):
        return path, value
    if isinstance(value, JSON_LEAF_TYPES):
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            found = find_json_failure(
                item,
                (*path, str(key)),
                reject_non_finite=reject_non_finite,
            )
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = find_json_failure(
                item,
                (*path, index),
                reject_non_finite=reject_non_finite,
            )
            if found is not None:
                return found
        return None
    return path, value
