"""Contract tests for the JSON-safe conversion engine.

Ported from whetstone-ai's serialization contract tests (generic parts
only; the DSPy handler tests stayed app-side with the handlers).

Deliberately not covered here:
- Full round-trip / lossless serialization
- Exhaustive Python type zoo (datetime, Decimal, UUID)
- Exact preview truncation byte lengths
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from dr_serialize import (
    POSTGRES_JSONB_MAX_BYTES,
    JsonEncodeError,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationError,
    SerializationLimits,
    postgres_jsonb_limits,
    serialization,
    to_jsonable,
    to_metadata_dict,
)
from tests.support import (
    BadModel,
    SerializedNameModel,
    SimpleObject,
    assert_diagnostics,
    assert_to_jsonable,
    bad_pydantic_model,
    large_payload,
    nested_list,
    ok_pydantic_model,
)

DEFAULT_LIMITS = postgres_jsonb_limits()
DEFAULT_MAX_DEPTH = DEFAULT_LIMITS.max_depth


class TestToJsonableInvariants:
    @pytest.mark.parametrize(
        ("input_value", "check"),
        [
            (None, lambda r: r is None),
            (True, lambda r: r is True),
            (42, lambda r: r == 42),
            (1.5, lambda r: r == 1.5),
            ("hi", lambda r: r == "hi"),
            ({"a": 1, "b": {"c": 2}}, lambda r: r == {"a": 1, "b": {"c": 2}}),
            ([1, [2, 3]], lambda r: r == [1, [2, 3]]),
            ((1, 2), lambda r: r == [1, 2]),
            ({1, 2}, lambda r: sorted(r) == [1, 2]),
            (frozenset({3}), lambda r: r == [3]),
            ({1: "one"}, lambda r: r == {"1": "one"}),
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
            "set_to_list",
            "frozenset_to_list",
            "int_dict_key_to_str",
        ],
    )
    def test_happy_path(
        self,
        input_value: Any,
        check: Any,
    ) -> None:
        result = assert_to_jsonable(input_value)
        assert check(result)

    def test_message_shaped_payload(self) -> None:
        payload = {"messages": [{"role": "user", "content": "hello"}]}
        assert assert_to_jsonable(payload) == payload


class TestBuiltinTransforms:
    @pytest.mark.parametrize(
        ("type_value", "expected_substring"),
        [
            (int, "int"),
            (SimpleObject, "SimpleObject"),
        ],
        ids=["builtin_type", "local_class"],
    )
    def test_plain_type(
        self,
        type_value: type,
        expected_substring: str,
    ) -> None:
        result = assert_to_jsonable(type_value)
        assert isinstance(result, str)
        assert result.startswith("<class ")
        assert expected_substring in result

    def test_pydantic_model(self) -> None:
        model = ok_pydantic_model()
        assert assert_to_jsonable(model) == model.model_dump(mode="json")

    def test_pydantic_precedence_over_object_vars(self) -> None:
        model = SerializedNameModel(name="n")
        result = assert_to_jsonable(model)
        assert result == model.model_dump(mode="json")
        assert result["name"] == "N"
        assert vars(model)["name"] == "n"

    def test_bytes(self) -> None:
        assert assert_to_jsonable(b"hello") == "<bytes len=5>"

    def test_generator(self) -> None:
        def gen() -> Any:
            yield 1

        result = assert_to_jsonable(gen())
        assert result == "<generator>"

    def test_coroutine(self) -> None:
        async def coro() -> None:
            return None

        with pytest.warns(
            RuntimeWarning,
            match="coroutine .* was never awaited",
        ):
            result = assert_to_jsonable(coro())
        assert result == "<coroutine>"

    def test_simple_object_vars(self) -> None:
        result = assert_to_jsonable(SimpleObject())
        assert result == {"a": 1, "label": "test"}


class TestGuardrails:
    def test_max_depth_exceeded(self) -> None:
        with pytest.raises(MaxDepthExceededError) as exc_info:
            to_jsonable(nested_list(101), limits=DEFAULT_LIMITS)
        exc = exc_info.value
        assert exc.depth == 101
        assert exc.max_depth == DEFAULT_MAX_DEPTH
        assert_diagnostics(
            exc,
            {"path", "detail", "depth", "max_depth", "value_preview"},
            depth=101,
            max_depth=DEFAULT_MAX_DEPTH,
        )

    def test_max_depth_nested_path(self) -> None:
        payload = {"outer": {"inner": nested_list(101)}}
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

    def test_hard_max_bytes_defaults_to_max_bytes(self) -> None:
        limits = SerializationLimits(max_bytes=100)
        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(large_payload(500), limits=limits)
        assert exc_info.value.postgres_max_bytes == 100

    def test_serialization_limits_are_frozen(self) -> None:
        limits = SerializationLimits(max_bytes=100)

        with pytest.raises(ValidationError, match="frozen"):
            limits.max_bytes = 200

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
            to_jsonable(bad_pydantic_model(), limits=DEFAULT_LIMITS)
        assert_diagnostics(
            exc_info.value,
            {"path", "detail", "value_preview", "underlying"},
        )

    def test_object_vars_serialization_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = SimpleObject()
        original = serialization.convert_value

        def patched(
            x: Any,
            depth: int = 0,
            path: tuple[str | int, ...] = (),
        ) -> Any:
            if path == ("label",):
                raise RuntimeError("vars walk failed")
            return original(x, depth, path)

        monkeypatch.setattr(serialization, "convert_value", patched)
        with pytest.raises(ObjectVarsSerializationError) as exc_info:
            to_jsonable(target, limits=DEFAULT_LIMITS)
        assert_diagnostics(
            exc_info.value,
            {"path", "detail", "value_preview", "underlying"},
        )

    def test_all_serialization_errors_implement_diagnostics(self) -> None:
        """Smoke: concrete subclasses return diagnostics without raising."""
        triggers: list[
            tuple[type[SerializationError], SerializationError]
        ] = []

        with pytest.raises(MaxDepthExceededError) as exc_info:
            to_jsonable(nested_list(101), limits=DEFAULT_LIMITS)
        triggers.append((MaxDepthExceededError, exc_info.value))

        with pytest.raises(JsonEncodeError) as exc_info:
            to_jsonable({"bad": object()}, limits=DEFAULT_LIMITS)
        triggers.append((JsonEncodeError, exc_info.value))

        with pytest.raises(PayloadTooLargeError) as exc_info:
            to_jsonable(
                large_payload(500),
                limits=postgres_jsonb_limits(100),
            )
        triggers.append((PayloadTooLargeError, exc_info.value))

        with pytest.raises(ModelDumpError) as exc_info:
            to_jsonable(BadModel(x=object()), limits=DEFAULT_LIMITS)
        triggers.append((ModelDumpError, exc_info.value))

        for exc_type, exc in triggers:
            diag = exc.diagnostics()
            assert isinstance(diag, dict)
            assert "path" in diag
            assert issubclass(type(exc), exc_type)


class TestMetadataAndEdgePaths:
    def test_to_metadata_dict_passthrough_dict_on_serialization_error(
        self,
    ) -> None:
        payload = {"bad": nested_list(101)}
        metadata = to_metadata_dict(payload)

        assert metadata == payload

    def test_to_metadata_dict_returns_empty_for_non_dict_failure(self) -> None:
        assert to_metadata_dict(nested_list(101)) == {}

    def test_to_metadata_dict_wraps_scalar_success(self) -> None:
        assert to_metadata_dict("hello") == {"response": "hello"}

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
