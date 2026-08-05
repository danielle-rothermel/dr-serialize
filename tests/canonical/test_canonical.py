"""Contract tests for Canonical JSON Text and hashes.

The golden fixture in ``tests/fixtures/hashing_golden.json`` pins exact
canonical text and hash values as the compatibility gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

from dr_serialize import (
    Jsonable,
    JsonEncodeError,
    Sha256Digest,
    canonical_json,
    canonical_json_bytes,
    canonical_sorted_values,
    json_hash,
)
from dr_serialize._core.digests import SHA256_HEX_LENGTH
from dr_serialize._core.json_values import find_json_failure

GOLDEN_FIXTURE = Path(__file__).parents[1] / "fixtures" / "hashing_golden.json"
GOLDEN_TRUNCATED_LENGTH = 16


def test_canonical_json_sorts_keys_and_compacts() -> None:
    value: Jsonable = {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}}
    assert canonical_json(value) == (
        '{"a":[1,2],"b":1,"c":{"y":true,"z":null}}'
    )


def test_canonical_json_preserves_array_order() -> None:
    assert canonical_json([3, 1, 2]) == "[3,1,2]"
    value: Jsonable = {"b": ["z", "a", "m"], "a": [3, 1, 2]}
    assert canonical_json(value) == '{"a":[3,1,2],"b":["z","a","m"]}'


@pytest.mark.parametrize(
    "value",
    [
        {},
        None,
        {"nested": [1, {"x": True}]},
        "héllo 日本語 🎯",
        'line one\nline two\t"quoted" \\backslash',
        9007199254740992,
        1e300,
    ],
)
def test_canonical_bytes_are_exact_text_utf8(value: Jsonable) -> None:
    assert canonical_json_bytes(value) == canonical_json(value).encode("utf-8")


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(float("nan"))

    exc = exc_info.value
    assert exc.path == ()
    assert exc.type_name == "float"
    assert isinstance(exc.underlying, ValueError)


def test_json_hash_full_length() -> None:
    hash_value = json_hash({"k": "v"})
    assert len(hash_value) == SHA256_HEX_LENGTH
    assert hash_value == json_hash({"k": "v"})


@pytest.mark.parametrize(
    ("function", "expected_hints"),
    [
        (canonical_json, {"value": Jsonable, "return": str}),
        (canonical_json_bytes, {"value": Jsonable, "return": bytes}),
        (
            canonical_sorted_values,
            {"values": Iterable[Jsonable], "return": list[Jsonable]},
        ),
        (
            json_hash,
            {
                "value": Jsonable,
                "length": int | None,
                "return": Sha256Digest | str,
            },
        ),
    ],
)
def test_canonical_runtime_annotations_resolve(
    function: Callable[..., object],
    expected_hints: dict[str, object],
) -> None:
    hints = get_type_hints(function)
    for name, expected in expected_hints.items():
        assert hints[name] == expected


@pytest.mark.parametrize("length", [1, 16, 24, 32, 64])
def test_json_hash_truncation(length: int) -> None:
    hash_value = json_hash({"k": "v"}, length=length)
    assert len(hash_value) == length
    assert json_hash({"k": "v"}).startswith(hash_value)


@pytest.mark.parametrize("length", [0, -1, 65])
def test_json_hash_rejects_bad_length(length: int) -> None:
    with pytest.raises(ValueError, match="hash length"):
        json_hash({"k": "v"}, length=length)


class TestCanonicalTypedErrors:
    def test_non_jsonable_value_is_rejected_before_encoding(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def unexpected_dump(_value: object, **_kwargs: object) -> str:
            pytest.fail("json.dumps must not receive a non-Jsonable value")

        monkeypatch.setattr(
            "dr_serialize.canonical.json_text.json.dumps",
            unexpected_dump,
        )

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", (1, 2)))

        assert exc_info.value.path == ()
        assert isinstance(exc_info.value.underlying, TypeError)

    def test_non_jsonable_leaf_raises_json_encode_error_with_path(
        self,
    ) -> None:
        value = cast("Jsonable", {"k": [1, object()]})
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(value)

        exc = exc_info.value
        assert exc.path == ("k", 1)
        assert exc.type_name == "object"
        assert isinstance(exc.underlying, TypeError)
        assert set(exc.diagnostics()) == {
            "path",
            "detail",
            "type_name",
            "value_preview",
            "underlying",
        }

    def test_non_finite_float_raises_json_encode_error(self) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json({"x": float("nan")})

        exc = exc_info.value
        assert exc.path == ("x",)
        assert exc.type_name == "float"
        assert isinstance(exc.underlying, ValueError)

    def test_non_string_key_raises_type_error_underlying(self) -> None:
        value = cast("Jsonable", {"outer": {1: "value"}})
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(value)

        exc = exc_info.value
        assert exc.path == ("outer",)
        assert exc.type_name == "int"
        assert isinstance(exc.underlying, TypeError)

    def test_hash_propagates_json_encode_error(self) -> None:
        value = cast("Jsonable", {"k": object()})
        with pytest.raises(JsonEncodeError):
            json_hash(value)

    def test_canonical_bytes_preserve_rejection(self) -> None:
        value = cast("Jsonable", {"k": object()})
        with pytest.raises(JsonEncodeError):
            canonical_json_bytes(value)

    def test_hash_length_validation_stays_value_error(self) -> None:
        with pytest.raises(ValueError, match="hash length"):
            json_hash({"a": 1}, length=0)


class TestCycleAndKeyDiagnostics:
    def test_cyclic_dict_raises_json_encode_error(self) -> None:
        cyclic: dict[str, Any] = {"a": 1}
        cyclic["self"] = cyclic
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", cyclic))
        assert isinstance(exc_info.value.underlying, TypeError)
        with pytest.raises(JsonEncodeError):
            json_hash(cast("Jsonable", cyclic))

    def test_cyclic_list_raises_json_encode_error(self) -> None:
        cyclic: list[Any] = [1, 2]
        cyclic.append(cyclic)
        with pytest.raises(JsonEncodeError):
            canonical_json(cast("Jsonable", cyclic))
        with pytest.raises(JsonEncodeError):
            json_hash(cast("Jsonable", cyclic))

    def test_find_json_failure_reports_non_string_key_with_path(
        self,
    ) -> None:
        found = find_json_failure({"outer": {1: 2}})
        assert found is not None
        path, leaf = found
        assert path == ("outer",)
        assert leaf == 1

    def test_find_json_failure_reports_top_level_non_string_key(
        self,
    ) -> None:
        found = find_json_failure({1: 2})
        assert found is not None
        path, leaf = found
        assert path == ()
        assert leaf == 1

    def test_find_json_failure_reports_cycle_instead_of_recursing(
        self,
    ) -> None:
        cyclic: dict[str, Any] = {}
        cyclic["self"] = cyclic
        found = find_json_failure(cyclic)
        assert found is not None
        path, _leaf = found
        assert path == ("self",)


class TestCanonicalSortedValues:
    def test_canonical_sorted_values_uses_text_not_collation(self) -> None:
        assert canonical_sorted_values([2, 10, 1]) == [1, 10, 2]

    def test_canonical_sorted_values_puts_booleans_after_numbers(self) -> None:
        assert canonical_sorted_values([True, 2, 10]) == [10, 2, True]

    def test_canonical_sorted_values_orders_incomparable_types(self) -> None:
        values: list[Jsonable] = [
            {"b": 1},
            None,
            "text",
            [1, 2],
            3,
            True,
        ]
        with pytest.raises(TypeError):
            sorted(cast("list[Any]", values))

        assert canonical_sorted_values(values) == [
            "text",
            3,
            [1, 2],
            None,
            True,
            {"b": 1},
        ]

    def test_canonical_sorted_values_orders_nested_values(self) -> None:
        values: list[Jsonable] = [
            {"b": 1, "a": 2},
            {"a": 2, "b": 1},
            {"a": 1},
        ]
        assert canonical_sorted_values(values) == [
            {"a": 1},
            {"b": 1, "a": 2},
            {"a": 2, "b": 1},
        ]

    def test_canonical_sorted_values_orders_non_ascii_by_escapes(self) -> None:
        # "é" canonicalizes to "é", whose leading backslash sorts before
        # every ASCII letter -- escape order, not human collation.
        assert canonical_sorted_values(["é", "z", "a"]) == ["é", "a", "z"]

    def test_canonical_sorted_values_consumes_generator_once(
        self,
    ) -> None:
        def values() -> Any:
            yield from ["b", "a", "b", "a"]

        assert canonical_sorted_values(values()) == ["a", "a", "b", "b"]

    def test_canonical_sorted_values_keeps_int_float_bool_distinct(
        self,
    ) -> None:
        result = canonical_sorted_values([True, 1.0, 1])
        assert result == [1, 1.0, True]
        assert [canonical_json(value) for value in result] == [
            "1",
            "1.0",
            "true",
        ]

    def test_canonical_sorted_values_handles_empty_input(self) -> None:
        assert canonical_sorted_values([]) == []

    def test_canonical_sorted_values_does_not_mutate_input(self) -> None:
        values: list[Jsonable] = ["c", "a", "b"]
        assert canonical_sorted_values(values) == ["a", "b", "c"]
        assert values == ["c", "a", "b"]

    def test_canonical_sorted_values_is_stable_across_orderings(self) -> None:
        values: list[Jsonable] = [{"k": 2}, "a", 1, [3]]
        assert canonical_sorted_values(values) == canonical_sorted_values(
            list(reversed(values))
        )

    def test_canonical_sorted_values_is_exported(self) -> None:
        import dr_serialize

        assert "canonical_sorted_values" in dr_serialize.__all__
        assert dr_serialize.canonical_sorted_values is canonical_sorted_values

    def test_canonical_sorted_values_prefixes_index_onto_path(self) -> None:
        values = cast("list[Jsonable]", ["ok", {"k": [object()]}])
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_sorted_values(values)

        exc = exc_info.value
        assert exc.path == (1, "k", 0)
        assert exc.type_name == "object"
        assert isinstance(exc.underlying, TypeError)
        assert isinstance(exc.__cause__, JsonEncodeError)
        assert exc.__cause__.path == ("k", 0)

    def test_canonical_sorted_values_prefixes_index_for_non_finite(
        self,
    ) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_sorted_values([1, float("nan")])

        exc = exc_info.value
        assert exc.path == (1,)
        assert exc.type_name == "float"
        assert isinstance(exc.underlying, ValueError)

    def test_canonical_sorted_values_reports_first_failure(self) -> None:
        values = cast("list[Jsonable]", [object(), object()])
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_sorted_values(values)

        assert exc_info.value.path == (0,)


class TestPydanticFieldSerializerPattern:
    def test_canonical_sorted_values_makes_model_dump_stable(self) -> None:
        import pydantic

        class TaggedModel(pydantic.BaseModel):
            tags: frozenset[str]

            @pydantic.field_serializer("tags")
            def serialize_tags(self, value: frozenset[str]) -> list[Jsonable]:
                return canonical_sorted_values(value)

        members = ["delta", "alpha", "charlie", "bravo", "10", "2"]
        forward = TaggedModel(tags=frozenset(members))
        reverse = TaggedModel(tags=frozenset(reversed(members)))

        expected = {
            "tags": ["10", "2", "alpha", "bravo", "charlie", "delta"],
        }
        assert forward.model_dump(mode="json") == expected
        assert reverse.model_dump(mode="json") == expected
        assert canonical_json_bytes(
            forward.model_dump(mode="json")
        ) == canonical_json_bytes(reverse.model_dump(mode="json"))


def _golden_cases() -> dict[str, dict[str, Any]]:
    return json.loads(GOLDEN_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("name", sorted(_golden_cases()))
def test_golden_hashing_case_reproduces(name: str) -> None:
    case = _golden_cases()[name]
    value = case["value"]
    assert canonical_json(value) == case["canonical_json"]
    assert canonical_json_bytes(value) == case["canonical_json"].encode()
    assert json_hash(value) == case["hash"]
    assert (
        json_hash(value, length=GOLDEN_TRUNCATED_LENGTH)
        == case["truncated_hash"]
    )
