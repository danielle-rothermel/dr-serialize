"""Contract tests for the normalization consumer handler API."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import pytest

from dr_serialize import (
    ConversionContext,
    JsonableHandle,
    JsonEncodeError,
    MaxDepthExceededError,
    SerializationLimits,
    Serializer,
    ValueTransformError,
    detail_repr,
    postgres_jsonb_limits,
    preview_repr,
)

DEFAULT_LIMITS = postgres_jsonb_limits()


class Marker:
    def __init__(self, tag: str) -> None:
        self.tag = tag


class Wrapper:
    def __init__(self, inner: Any) -> None:
        self.inner = inner


class Direct:
    def __init__(self, value: Any) -> None:
        self.value = value


def marker_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if isinstance(x, Marker):
        return True, {"marker": x.tag}
    return False, None


def wrapper_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, Wrapper):
        return True, {"inner": ctx.convert(x.inner, "inner")}
    return False, None


def direct_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if isinstance(x, Direct):
        return True, x.value
    return False, None


def test_handler_intercepts_before_fallbacks() -> None:
    # Without the handler, Marker falls through to the __dict__ walk.
    plain = Serializer(limits=DEFAULT_LIMITS)
    assert plain.to_jsonable(Marker("t")) == {"tag": "t"}

    with_handler = Serializer(
        limits=DEFAULT_LIMITS, handlers=(marker_handler,)
    )
    assert with_handler.to_jsonable(Marker("t")) == {"marker": "t"}


def test_serializers_do_not_share_handlers() -> None:
    with_handler = Serializer(
        limits=DEFAULT_LIMITS, handlers=(marker_handler,)
    )
    plain = Serializer(limits=DEFAULT_LIMITS)
    assert with_handler.to_jsonable(Marker("t")) == {"marker": "t"}
    assert plain.to_jsonable(Marker("t")) == {"tag": "t"}


def test_scalars_bypass_consumer_handlers() -> None:
    def greedy(x: Any, ctx: ConversionContext) -> JsonableHandle:
        del ctx
        return True, f"intercepted {x!r}"

    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(greedy,))
    assert serializer.to_jsonable(42) == 42
    assert serializer.to_jsonable([1, 2]) == [1, 2]


def test_handler_recurses_via_ctx_convert() -> None:
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(wrapper_handler,))
    result = serializer.to_jsonable(Wrapper(Marker("deep")))
    assert result == {"inner": {"tag": "deep"}}


def test_valid_direct_handler_output_is_preserved() -> None:
    value = {"items": [1, "two", None]}
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(direct_handler,))

    assert serializer.to_jsonable(Direct(value)) is value


def test_non_finite_direct_handler_output_is_preserved() -> None:
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(direct_handler,))

    result = serializer.to_jsonable(Direct(float("nan")))

    assert isinstance(result, float)
    assert math.isnan(result)


def test_direct_handler_output_rejects_invalid_nested_leaf_with_path() -> None:
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(direct_handler,))

    with pytest.raises(JsonEncodeError) as exc_info:
        serializer.to_jsonable({"outer": Direct({"items": [object()]})})

    assert exc_info.value.path == ("outer", "items", 0)


def test_direct_handler_output_rejects_non_string_key() -> None:
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(direct_handler,))

    with pytest.raises(JsonEncodeError) as exc_info:
        serializer.to_jsonable({"outer": Direct({1: "value"})})

    assert exc_info.value.path == ("outer",)
    assert exc_info.value.type_name == "int"


def test_direct_handler_output_rejects_cycle() -> None:
    value: list[Any] = []
    value.append(value)
    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(direct_handler,))

    with pytest.raises(JsonEncodeError) as exc_info:
        serializer.to_jsonable(Direct(value))

    assert exc_info.value.path == (0,)


def test_direct_handler_output_accepts_exact_max_depth() -> None:
    serializer = Serializer(
        limits=SerializationLimits(max_depth=2, max_bytes=1_000_000),
        handlers=(direct_handler,),
    )

    assert serializer.to_jsonable(Direct({"items": ["leaf"]})) == {
        "items": ["leaf"]
    }


def test_direct_handler_output_rejects_one_past_max_depth_with_path() -> None:
    serializer = Serializer(
        limits=SerializationLimits(max_depth=3, max_bytes=1_000_000),
        handlers=(direct_handler,),
    )

    with pytest.raises(MaxDepthExceededError) as exc_info:
        serializer.to_jsonable({"outer": Direct({"items": [["leaf"]]})})

    assert exc_info.value.depth == 4
    assert exc_info.value.max_depth == 3
    assert exc_info.value.path == ("outer", "items", 0, 0)


def test_ctx_convert_enforces_max_depth() -> None:
    value: Any = "leaf"
    for _ in range(5):
        value = Wrapper(value)
    limits = SerializationLimits(max_depth=3, max_bytes=1_000_000)
    serializer = Serializer(limits=limits, handlers=(wrapper_handler,))
    with pytest.raises(MaxDepthExceededError):
        serializer.to_jsonable(value)


def test_value_transform_error_subclass_carries_prefix_and_shape() -> None:
    class CustomTransformError(ValueTransformError):
        message_prefix: ClassVar[str] = "custom transform failed"

    def failing_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
        if isinstance(x, Marker):
            underlying = RuntimeError("boom")
            raise CustomTransformError(
                path=ctx.path,
                underlying=underlying,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            )
        return False, None

    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(failing_handler,))
    with pytest.raises(CustomTransformError) as exc_info:
        serializer.to_jsonable({"k": Marker("t")})
    exc = exc_info.value
    assert str(exc) == "custom transform failed at path ('k',)"
    assert set(exc.diagnostics()) == {
        "path",
        "detail",
        "value_preview",
        "underlying",
    }
    assert exc.diagnostics()["path"] == ["k"]
