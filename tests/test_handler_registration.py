"""Contract tests for the consumer handler registration API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from dr_serialize import (
    JsonPath,
    ValueTransformError,
    clear_registered_handlers,
    convert_value,
    detail_repr,
    postgres_jsonb_limits,
    preview_repr,
    register_handler,
    registered_handlers,
    to_jsonable,
)

DEFAULT_LIMITS = postgres_jsonb_limits()


class Marker:
    def __init__(self, tag: str) -> None:
        self.tag = tag


def marker_handler(x: Any, depth: int, path: JsonPath) -> tuple[bool, Any]:
    del depth, path
    if isinstance(x, Marker):
        return True, {"marker": x.tag}
    return False, None


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[None]:
    clear_registered_handlers()
    yield
    clear_registered_handlers()


def test_registered_handler_intercepts_before_fallbacks() -> None:
    # Without registration, Marker falls through to the __dict__ walk.
    assert to_jsonable(Marker("t"), limits=DEFAULT_LIMITS) == {"tag": "t"}

    register_handler(marker_handler)
    assert to_jsonable(Marker("t"), limits=DEFAULT_LIMITS) == {"marker": "t"}


def test_registration_is_idempotent() -> None:
    register_handler(marker_handler)
    register_handler(marker_handler)
    assert registered_handlers().count(marker_handler) == 1


def test_scalars_bypass_registered_handlers() -> None:
    def greedy(x: Any, depth: int, path: JsonPath) -> tuple[bool, Any]:
        del depth, path
        return True, f"intercepted {x!r}"

    register_handler(greedy)
    assert to_jsonable(42, limits=DEFAULT_LIMITS) == 42
    assert to_jsonable([1, 2], limits=DEFAULT_LIMITS) == [1, 2]


def test_handler_can_recurse_via_convert_value() -> None:
    class Wrapper:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

    def wrapper_handler(
        x: Any, depth: int, path: JsonPath
    ) -> tuple[bool, Any]:
        if isinstance(x, Wrapper):
            return True, {
                "inner": convert_value(x.inner, depth + 1, (*path, "inner"))
            }
        return False, None

    register_handler(wrapper_handler)
    result = to_jsonable(
        Wrapper(Marker("deep")),
        limits=DEFAULT_LIMITS,
    )
    assert result == {"inner": {"tag": "deep"}}


def test_value_transform_error_subclass_carries_prefix_and_shape() -> None:
    class CustomTransformError(ValueTransformError):
        message_prefix: ClassVar[str] = "custom transform failed"

    def failing_handler(
        x: Any, depth: int, path: JsonPath
    ) -> tuple[bool, Any]:
        del depth
        if isinstance(x, Marker):
            underlying = RuntimeError("boom")
            raise CustomTransformError(
                path=path,
                underlying=underlying,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            )
        return False, None

    register_handler(failing_handler)
    with pytest.raises(CustomTransformError) as exc_info:
        to_jsonable({"k": Marker("t")}, limits=DEFAULT_LIMITS)
    exc = exc_info.value
    assert str(exc) == "custom transform failed at path ('k',)"
    assert set(exc.diagnostics()) == {
        "path",
        "detail",
        "value_preview",
        "underlying",
    }
    assert exc.diagnostics()["path"] == ["k"]
