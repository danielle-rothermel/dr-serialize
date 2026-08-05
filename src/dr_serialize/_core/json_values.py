"""JSON value types and neutral failure classification shared by all areas.

The normalization engine (:class:`~dr_serialize.normalization.Serializer`)
produces ``Jsonable``; the Canonical JSON Text utilities
(:func:`~dr_serialize.canonical.canonical_json`,
:func:`~dr_serialize.canonical.json_hash`) and the identity area
(:mod:`dr_serialize.identity`) consume it.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from dr_serialize._core.diagnostics import JsonPath

type Jsonable = (
    None | bool | int | float | str | list[Jsonable] | dict[str, Jsonable]
)

type _JsonFailureReason = Literal[
    "maximum container depth",
    "maximum integer digits",
    "non-finite number",
    "non-string object key",
    "reference cycle",
    "unsupported type",
]


@dataclass(frozen=True, slots=True)
class _JsonFailure:
    path: JsonPath
    leaf: Any
    reason: _JsonFailureReason
    actual: int | None = None
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class _Visit:
    value: Any
    path: JsonPath
    parent_container_depth: int


@dataclass(frozen=True, slots=True)
class _ContainerFrame:
    iterator: Iterator[tuple[Any, Any]]
    path: JsonPath
    container_id: int
    container_depth: int
    is_object: bool


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
        reject_non_finite=reject_non_finite,
    )
    if failure is None:
        return None
    return failure.path, failure.leaf


def _find_strict_json_failure(
    value: Any,
    path: JsonPath = (),
) -> _JsonFailure | None:
    """Locate the first value outside the strict JSON data model."""
    return _walk_json_failure(
        value,
        path,
        reject_non_finite=True,
    )


def _find_bounded_strict_json_failure(
    value: Any,
    path: JsonPath = (),
    *,
    max_container_depth: int,
    max_integer_digits: int,
) -> _JsonFailure | None:
    """Locate the first strict JSON or selected profile-bound failure."""
    return _walk_json_failure(
        value,
        path,
        reject_non_finite=True,
        max_container_depth=max_container_depth,
        max_integer_digits=max_integer_digits,
    )


def _walk_json_failure(  # noqa: PLR0911,PLR0912 -- exhaustive JSON value walk
    value: Any,
    path: JsonPath,
    *,
    reject_non_finite: bool,
    max_container_depth: int | None = None,
    max_integer_digits: int | None = None,
) -> _JsonFailure | None:
    """Iteratively walk a JSON-shaped value in depth-first order.

    ``active_container_ids`` holds every container on the current path.
    Re-entering one is a reference cycle; completing a frame removes it so a
    repeated shared subtree remains valid. Iterator frames preserve the
    recursive walk's first-failure order, including validating each object key
    immediately before its value.
    """
    integer_limit = (
        10**max_integer_digits if max_integer_digits is not None else None
    )
    active_container_ids: set[int] = set()
    stack: list[_Visit | _ContainerFrame] = [_Visit(value, path, 0)]

    while stack:
        entry = stack.pop()
        if isinstance(entry, _ContainerFrame):
            try:
                key, item = next(entry.iterator)
            except StopIteration:
                active_container_ids.remove(entry.container_id)
                continue

            stack.append(entry)
            if entry.is_object and not isinstance(key, str):
                return _JsonFailure(
                    path=entry.path,
                    leaf=key,
                    reason="non-string object key",
                )
            stack.append(
                _Visit(
                    item,
                    (*entry.path, key),
                    entry.container_depth,
                )
            )
            continue

        current = entry.value
        if (
            reject_non_finite
            and isinstance(current, float)
            and not math.isfinite(current)
        ):
            return _JsonFailure(
                path=entry.path,
                leaf=current,
                reason="non-finite number",
            )
        if isinstance(current, bool) or current is None:
            continue
        if isinstance(current, int):
            if (
                integer_limit is not None
                and int.__abs__(current) >= integer_limit
            ):
                return _JsonFailure(
                    path=entry.path,
                    leaf=current,
                    reason="maximum integer digits",
                    maximum=max_integer_digits,
                )
            continue
        if isinstance(current, (float, str)):
            continue
        if isinstance(current, (dict, list)):
            container_id = id(current)
            if container_id in active_container_ids:
                return _JsonFailure(
                    path=entry.path,
                    leaf=current,
                    reason="reference cycle",
                )

            container_depth = entry.parent_container_depth + 1
            if (
                max_container_depth is not None
                and container_depth > max_container_depth
            ):
                return _JsonFailure(
                    path=entry.path,
                    leaf=current,
                    reason="maximum container depth",
                    actual=container_depth,
                    maximum=max_container_depth,
                )

            active_container_ids.add(container_id)
            iterator: Iterator[tuple[Any, Any]]
            if isinstance(current, dict):
                iterator = iter(current.items())
                is_object = True
            else:
                iterator = iter(enumerate(current))
                is_object = False
            stack.append(
                _ContainerFrame(
                    iterator=iterator,
                    path=entry.path,
                    container_id=container_id,
                    container_depth=container_depth,
                    is_object=is_object,
                )
            )
            continue
        return _JsonFailure(
            path=entry.path,
            leaf=current,
            reason="unsupported type",
        )

    return None
