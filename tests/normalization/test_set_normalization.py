"""Focused contracts for deterministic unordered collection normalization."""

from __future__ import annotations

import pytest

from dr_serialize import (
    JsonEncodeError,
    MaxDepthExceededError,
    SerializationLimits,
    postgres_jsonb_limits,
)
from tests.normalization.support import assert_to_jsonable, to_jsonable

DEFAULT_LIMITS = postgres_jsonb_limits()


def test_set_members_are_ordered_by_canonical_text() -> None:
    value = {"beta", "alpha", "10", "2", "gamma"}
    assert assert_to_jsonable(value) == [
        "10",
        "2",
        "alpha",
        "beta",
        "gamma",
    ]


def test_nested_set_members_are_ordered() -> None:
    value = {(2, "b"), (1, "a")}
    assert assert_to_jsonable(value) == [[1, "a"], [2, "b"]]


def test_lists_and_tuples_retain_original_order() -> None:
    assert assert_to_jsonable(["b", "a", "c"]) == ["b", "a", "c"]
    assert assert_to_jsonable(("b", "a", "c")) == ["b", "a", "c"]


def test_list_inside_set_member_retains_its_order() -> None:
    value = {("z", "a"), ("m",)}
    assert assert_to_jsonable(value) == [["m"], ["z", "a"]]


def test_non_finite_float_in_list_still_normalizes() -> None:
    result = to_jsonable([float("inf")], limits=DEFAULT_LIMITS)
    assert isinstance(result, list)
    assert result[0] == float("inf")


def test_max_depth_enforced_through_set_members() -> None:
    limits = SerializationLimits(max_depth=3, max_bytes=1_000_000)
    deep_member = (((("x",),),),)
    with pytest.raises(MaxDepthExceededError):
        to_jsonable({deep_member}, limits=limits)


def test_nested_non_finite_float_in_set_reports_full_path() -> None:
    value = {"a": {"b": {"c": {float("nan")}}}}
    with pytest.raises(JsonEncodeError) as exc_info:
        to_jsonable(value, limits=DEFAULT_LIMITS)

    exc = exc_info.value
    assert exc.path == ("a", "b", "c", 0)
    assert exc.type_name == "float"
    assert isinstance(exc.underlying, ValueError)


def test_deep_set_member_error_path_includes_member_interior() -> None:
    value = {"k": [{("outer", (lambda: None,))}]}
    with pytest.raises(JsonEncodeError) as exc_info:
        to_jsonable(value, limits=DEFAULT_LIMITS)

    assert exc_info.value.path == ("k", 0, 0, 1, 0)
