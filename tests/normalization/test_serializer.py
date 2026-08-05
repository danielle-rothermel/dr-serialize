from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from dr_serialize import (
    POSTGRES_JSONB_MAX_BYTES,
    JsonEncodeError,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationLimits,
    postgres_jsonb_limits,
)
from tests.normalization.support import (
    AttributeBackedObject,
    SerializedNameModel,
    assert_diagnostics,
    assert_to_jsonable,
    large_payload,
    nested_list,
    to_jsonable,
    unserializable_pydantic_model,
)

DEFAULT_LIMITS = postgres_jsonb_limits()
DEFAULT_MAX_DEPTH = DEFAULT_LIMITS.max_depth


class TestToJsonableInvariants:
    @pytest.mark.parametrize(
        ("input_value", "expected"),
        [
            (None, None),
            (True, True),
            (42, 42),
            (1.5, 1.5),
            ("hi", "hi"),
            ({"a": 1, "b": {"c": 2}}, {"a": 1, "b": {"c": 2}}),
            ([1, [2, 3]], [1, [2, 3]]),
            ((1, 2), [1, 2]),
            ({1: "one"}, {"1": "one"}),
        ],
        ids=[
            "none",
            "bool",
            "int",
            "float",
            "str",
            "nested_dict",
            "nested_list",
            "tuple_to_list",
            "int_dict_key_to_str",
        ],
    )
    def test_builtin_values_normalize_as_expected(
        self,
        input_value: Any,
        expected: Any,
    ) -> None:
        assert assert_to_jsonable(input_value) == expected


class TestBuiltinTransforms:
    @pytest.mark.parametrize(
        ("type_value", "expected_substring"),
        [
            (int, "int"),
            (AttributeBackedObject, "AttributeBackedObject"),
        ],
        ids=["builtin_type", "local_class"],
    )
    def test_type_objects_normalize_to_class_placeholders(
        self,
        type_value: type,
        expected_substring: str,
    ) -> None:
        result = assert_to_jsonable(type_value)
        assert isinstance(result, str)
        assert result.startswith("<class ")
        assert expected_substring in result

    def test_pydantic_field_serializer_precedes_object_vars(self) -> None:
        model = SerializedNameModel(name="n")
        result = assert_to_jsonable(model)
        assert result == model.model_dump(mode="json")
        assert result["name"] == "N"
        assert vars(model)["name"] == "n"

    def test_bytes_normalize_to_length_placeholder(self) -> None:
        assert assert_to_jsonable(b"hello") == "<bytes len=5>"

    def test_generator_normalizes_to_runtime_type_placeholder(self) -> None:
        def gen() -> Any:
            yield 1

        result = assert_to_jsonable(gen())
        assert result == "<generator>"

    def test_coroutine_normalizes_to_runtime_type_placeholder(self) -> None:
        async def coro() -> None:
            return None

        coroutine = coro()
        try:
            assert assert_to_jsonable(coroutine) == "<coroutine>"
        finally:
            coroutine.close()

    def test_plain_object_normalizes_from_instance_attributes(self) -> None:
        result = assert_to_jsonable(AttributeBackedObject())
        assert result == {"a": 1, "label": "test"}


class TestGuardrails:
    def test_max_depth_enforced_inside_model_dump(self) -> None:
        class PayloadModel(BaseModel):
            data: Any

        limits = SerializationLimits(max_depth=3, max_bytes=1_000_000)
        with pytest.raises(MaxDepthExceededError):
            to_jsonable(PayloadModel(data=nested_list(10)), limits=limits)

    def test_max_depth_exceeded(self) -> None:
        with pytest.raises(MaxDepthExceededError) as exc_info:
            to_jsonable(nested_list(201), limits=DEFAULT_LIMITS)
        exc = exc_info.value
        assert exc.depth == 201
        assert exc.max_depth == DEFAULT_MAX_DEPTH
        assert_diagnostics(
            exc,
            {"path", "detail", "depth", "max_depth", "value_preview"},
            depth=201,
            max_depth=DEFAULT_MAX_DEPTH,
        )

    def test_max_depth_nested_path(self) -> None:
        payload = {"outer": {"inner": nested_list(201)}}
        with pytest.raises(MaxDepthExceededError) as exc_info:
            to_jsonable(payload, limits=DEFAULT_LIMITS)
        path = exc_info.value.path
        assert path[0] == "outer"
        assert path[1] == "inner"

    def test_configured_max_depth_is_enforced(self) -> None:
        limits = DEFAULT_LIMITS.model_copy(update={"max_depth": 3})
        with pytest.raises(MaxDepthExceededError) as exc_info:
            to_jsonable(nested_list(10), limits=limits)
        assert exc_info.value.max_depth == 3

    def test_payload_too_large(self) -> None:
        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(
                large_payload(500),
                limits=postgres_jsonb_limits(100),
            )
        exc = exc_info.value
        assert exc.size_bytes > exc.max_bytes
        assert exc.max_bytes == 100
        assert exc.postgres_max_bytes == POSTGRES_JSONB_MAX_BYTES
        assert "blob" in exc.top_level_sizes
        assert exc.preview_head
        assert_diagnostics(
            exc,
            {
                "path",
                "detail",
                "size_bytes",
                "max_bytes",
                "postgres_max_bytes",
                "top_level_sizes",
                "preview_head",
                "preview_tail",
            },
            max_bytes=100,
            postgres_max_bytes=POSTGRES_JSONB_MAX_BYTES,
        )

    def test_max_bytes_remains_the_enforced_runtime_limit(self) -> None:
        limits = SerializationLimits(max_bytes=100, hard_max_bytes=1_000)
        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(large_payload(500), limits=limits)

        assert exc_info.value.max_bytes == 100
        assert exc_info.value.postgres_max_bytes == 1_000

    def test_hard_max_bytes_defaults_to_max_bytes(self) -> None:
        limits = SerializationLimits(max_bytes=100)
        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(large_payload(500), limits=limits)
        assert exc_info.value.postgres_max_bytes == 100

    def test_json_encode_error(self) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            to_jsonable({"bad": object()}, limits=DEFAULT_LIMITS)
        exc = exc_info.value
        assert exc.type_name == "object"
        assert exc.path == ("bad",)
        assert_diagnostics(
            exc,
            {"path", "detail", "type_name", "value_preview", "underlying"},
            path=["bad"],
            type_name="object",
        )


class TestStructuredErrors:
    def test_model_dump_error(self) -> None:
        with pytest.raises(ModelDumpError) as exc_info:
            to_jsonable(unserializable_pydantic_model(), limits=DEFAULT_LIMITS)
        assert_diagnostics(
            exc_info.value,
            {"path", "detail", "value_preview", "underlying"},
        )

    def test_object_vars_serialization_error(self) -> None:
        class BrokenVars(dict[str, Any]):
            def items(self) -> Any:
                raise RuntimeError("vars walk failed")

        class BrokenObject:
            @property
            def __dict__(self) -> BrokenVars:  # type: ignore[override]
                return BrokenVars(label="test")

        target = BrokenObject()
        with pytest.raises(ObjectVarsSerializationError) as exc_info:
            to_jsonable(target, limits=DEFAULT_LIMITS)
        assert_diagnostics(
            exc_info.value,
            {"path", "detail", "value_preview", "underlying"},
        )


class TestMetadataAndEdgePaths:
    def test_json_encode_error_reports_nested_path(self) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            to_jsonable({"a": [{"b": object()}]}, limits=DEFAULT_LIMITS)

        assert exc_info.value.path == ("a", 0, "b")

    def test_payload_too_large_error_uses_empty_tail_for_short_payload(
        self,
    ) -> None:
        payload = {"data": "x" * 120}
        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(payload, limits=postgres_jsonb_limits(100))

        assert exc_info.value.preview_tail == ""

    def test_async_generator_serializes_to_placeholder(self) -> None:
        async def async_gen() -> Any:
            yield 1

        result = to_jsonable(async_gen(), limits=DEFAULT_LIMITS)
        assert result == "<async_generator>"
