"""Contract tests for in-memory strict JSON value validation."""

from __future__ import annotations

from typing import Any

import pytest

from dr_serialize import StrictJsonError, validate_strict_json


def _nested_list(depth: int, leaf: Any = 0) -> Any:
    value = leaf
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -1,
        42,
        9007199254740992,
        0.0,
        -0.001,
        1e300,
        "",
        "text",
        [],
        {},
        [1, "two", None, True, [3, 4]],
        {"a": 1, "b": {"c": [None, False]}},
        {"nested": {"deep": {"deeper": [1, {"x": "y"}]}}},
    ],
)
def test_validate_strict_json_accepts_strict_json(value: Any) -> None:
    assert validate_strict_json(value) is value


def test_validate_strict_json_accepts_numeric_string_keys() -> None:
    value = {"10": "ten", "2": "two", "1": "one"}
    assert validate_strict_json(value) is value


def test_rejects_non_json_value_at_root() -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(object())
    exc = exc_info.value
    assert exc.path == ()
    assert exc.reason == "unsupported type"
    assert exc.type_name == "object"


def test_broken_repr_cannot_replace_strict_json_error() -> None:
    class BadRepr:
        def __repr__(self) -> str:
            raise RuntimeError("representation failed")

    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(BadRepr())

    assert exc_info.value.detail == "<repr failed for BadRepr: RuntimeError>"


def test_rejects_non_json_value_with_jsonpath_location() -> None:
    value = {"k": [1, object()]}
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.path == ("k", 1)
    assert exc.reason == "unsupported type"
    assert set(exc.diagnostics()) == {
        "path",
        "detail",
        "reason",
        "type_name",
    }
    assert exc.diagnostics()["path"] == ["k", 1]


@pytest.mark.parametrize(
    "bad_value", [float("nan"), float("inf"), float("-inf")]
)
def test_rejects_non_finite_number(bad_value: float) -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json({"x": [0.0, bad_value]})
    exc = exc_info.value
    assert exc.path == ("x", 1)
    assert exc.reason == "non-finite number"
    assert exc.type_name == "float"


@pytest.mark.parametrize("bad_key", [1, 2.0, None, True, (1, 2)])
def test_rejects_non_string_object_key(bad_key: Any) -> None:
    value = {"ok": {bad_key: "v"}}
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.path == ("ok",)
    assert exc.reason == "non-string object key"


def test_rejects_dict_reference_cycle() -> None:
    value: dict[str, Any] = {"a": 1}
    value["self"] = value
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.reason == "reference cycle"
    assert exc.type_name == "dict"


def test_rejects_list_reference_cycle() -> None:
    inner: list[Any] = [1]
    value = {"items": inner}
    inner.append(inner)
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.reason == "reference cycle"
    assert exc.type_name == "list"


def test_repeated_shared_subtree_is_not_a_cycle() -> None:
    shared = {"k": "v"}
    value = {"a": shared, "b": shared}
    assert validate_strict_json(value) is value


def test_deep_strict_json_validation_does_not_recurse() -> None:
    value = _nested_list(2_000)

    assert validate_strict_json(value) is value


def test_first_failure_order_remains_depth_first() -> None:
    value = {"first": [object()], 1: "later invalid key"}

    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)

    assert exc_info.value.path == ("first", 0)
    assert exc_info.value.reason == "unsupported type"


@pytest.mark.parametrize(
    "bad_value",
    [
        b"bytes",
        (1, 2),
        {1, 2},
        object(),
        complex(1, 2),
    ],
)
def test_rejects_assorted_non_json_types(bad_value: Any) -> None:
    with pytest.raises(StrictJsonError):
        validate_strict_json(bad_value)
