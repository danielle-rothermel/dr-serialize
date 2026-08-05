from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast, get_type_hints

import pytest

from dr_serialize import (
    Jsonable,
    JsonEncodeError,
    canonical_json,
    canonical_json_bytes,
    canonical_sorted_values,
)


def test_canonical_sorted_values_runtime_annotations_resolve() -> None:
    assert get_type_hints(canonical_sorted_values) == {
        "values": Iterable[Jsonable],
        "return": list[Jsonable],
    }


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
        # Non-ASCII strings are escaped, so "\\u00e9" sorts before ASCII
        # letters; this is canonical-text order, not human collation.
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
