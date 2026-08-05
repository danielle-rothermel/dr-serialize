"""Contract tests for bounded diagnostic representations."""

from __future__ import annotations

from typing import Any

import pytest

from dr_serialize import detail_repr, preview_repr
from dr_serialize._core.diagnostics import (
    DEBUG_DETAIL_LIMIT,
    MESSAGE_PREVIEW,
)


class RaisingRepr:
    def __repr__(self) -> str:
        raise RuntimeError("representation failed")


class NonStringRepr:
    def __repr__(self) -> Any:
        return 1


class LongRepr:
    def __repr__(self) -> str:
        return "x" * (DEBUG_DETAIL_LIMIT + 1)


class RaisingSlice(str):
    __slots__ = ()

    def __getitem__(self, key: object) -> str:
        raise LookupError("slice failed")


class RaisingSliceRepr:
    def __repr__(self) -> str:
        return RaisingSlice("rendered")


@pytest.mark.parametrize(
    ("value", "error_name"),
    [
        (RaisingRepr(), "RuntimeError"),
        (NonStringRepr(), "TypeError"),
    ],
)
@pytest.mark.parametrize("render", [preview_repr, detail_repr])
def test_broken_repr_returns_a_bounded_fallback(
    value: object,
    error_name: str,
    render: Any,
) -> None:
    result = render(value)
    assert result == f"<repr failed for {type(value).__name__}: {error_name}>"


def test_successful_repr_is_truncated_to_each_public_limit() -> None:
    value = LongRepr()
    assert preview_repr(value) == "x" * MESSAGE_PREVIEW
    assert detail_repr(value) == "x" * DEBUG_DETAIL_LIMIT


@pytest.mark.parametrize("render", [preview_repr, detail_repr])
def test_str_subclass_repr_cannot_override_bounding(render: Any) -> None:
    assert render(RaisingSliceRepr()) == "rendered"
