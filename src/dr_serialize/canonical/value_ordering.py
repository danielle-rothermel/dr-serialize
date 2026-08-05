"""Deterministic ordering for logically unordered JSON values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dr_serialize.canonical.errors import JsonEncodeError
from dr_serialize.canonical.json_text import canonical_json

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dr_serialize._core.json_values import Jsonable


def canonical_sorted_values(values: Iterable[Jsonable], /) -> list[Jsonable]:
    """Order ``values`` by their :func:`canonical_json` text.

    Projects a logically unordered collection -- a set, a frozenset, or any
    other iterable whose order carries no meaning -- into one deterministic
    JSON array. It must not be used to reorder a semantically ordered array,
    whose order is part of the value.

    The ordering is arbitrary-but-stable lexicographic order over canonical
    JSON text under the profile, not a human collation: ``10`` sorts before
    ``2``, ``true`` sorts after every number, and non-ASCII strings order by
    their ``\\uXXXX`` escapes. It supports heterogeneous and nested
    ``Jsonable`` values without relying on Python cross-type comparability.

    The helper is policy-free: it never normalizes, coerces, deduplicates, or
    selects domain fields. Duplicates are preserved (``1`` and ``1.0`` render
    as distinct canonical texts and both survive), and ``values`` is consumed
    exactly once. Members outside strict ``Jsonable`` fail through
    :class:`JsonEncodeError` with the member's index in the input iterable
    prefixed onto the error path; for set-derived input that index is
    arbitrary but reproducible within the call.

    Downstream Pydantic models project unordered fields through it in a
    ``field_serializer``, so ``model_dump(mode="json")`` is deterministic::

        class Model(pydantic.BaseModel):
            tags: frozenset[str]

            @pydantic.field_serializer("tags")
            def serialize_tags(self, value: frozenset[str]) -> list[Jsonable]:
                return canonical_sorted_values(value)
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
