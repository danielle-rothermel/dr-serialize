from __future__ import annotations

from collections.abc import Iterable  # noqa: TC003 -- runtime hints

from dr_serialize._core.json_values import (
    Jsonable,  # noqa: TC001 -- runtime hints
)
from dr_serialize.canonical.errors import JsonEncodeError
from dr_serialize.canonical.json_text import canonical_json


def canonical_sorted_values(values: Iterable[Jsonable], /) -> list[Jsonable]:
    """Project a logically unordered iterable into canonical-text order.

    Do not use this for semantically ordered arrays. Sorting is lexicographic
    over profile v1 canonical JSON text, not Python or human ordering. The
    iterable is consumed once, duplicates are preserved, and no normalization
    or coercion occurs. A failing member's input index is prefixed to
    ``JsonEncodeError.path``.
    """
    keyed: list[tuple[str, Jsonable]] = []
    for index, value in enumerate(values):
        try:
            keyed.append((canonical_json(value), value))
        except JsonEncodeError as error:
            raise JsonEncodeError(
                path=(index, *error.path),
                type_name=error.type_name,
                detail=error.detail,
                underlying=error.underlying,
                value_preview=error.value_preview,
            ) from error
    keyed.sort(key=lambda entry: entry[0])
    return [value for _text, value in keyed]
