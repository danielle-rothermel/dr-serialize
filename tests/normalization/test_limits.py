from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from dr_serialize import SerializationLimits


def test_default_max_depth_is_200() -> None:
    assert SerializationLimits(max_bytes=0).max_depth == 200


@pytest.mark.parametrize(
    "field",
    ["max_depth", "max_bytes", "hard_max_bytes"],
)
def test_negative_serialization_limit_is_rejected(field: str) -> None:
    values: dict[str, Any] = {
        "max_depth": 0,
        "max_bytes": 0,
        "hard_max_bytes": 0,
    }
    values[field] = -1

    with pytest.raises(ValidationError):
        SerializationLimits(**values)


@pytest.mark.parametrize(
    "field",
    ["max_depth", "max_bytes", "hard_max_bytes"],
)
def test_boolean_serialization_limit_is_rejected(field: str) -> None:
    values: dict[str, Any] = {
        "max_depth": 0,
        "max_bytes": 0,
        "hard_max_bytes": 0,
    }
    values[field] = False

    with pytest.raises(ValidationError):
        SerializationLimits(**values)


def test_max_bytes_cannot_exceed_hard_max_bytes() -> None:
    with pytest.raises(
        ValidationError,
        match="max_bytes must not exceed hard_max_bytes",
    ):
        SerializationLimits(max_bytes=101, hard_max_bytes=100)


@pytest.mark.parametrize(
    ("limits", "effective_hard_max_bytes"),
    [
        (
            SerializationLimits(
                max_depth=0,
                max_bytes=0,
                hard_max_bytes=0,
            ),
            0,
        ),
        (
            SerializationLimits(max_bytes=100, hard_max_bytes=100),
            100,
        ),
        (SerializationLimits(max_bytes=100, hard_max_bytes=None), 100),
    ],
    ids=["zero", "equal", "none"],
)
def test_effective_hard_max_bytes(
    limits: SerializationLimits,
    effective_hard_max_bytes: int,
) -> None:
    assert limits.effective_hard_max_bytes == effective_hard_max_bytes


def test_serialization_limits_are_frozen() -> None:
    limits = SerializationLimits(max_bytes=100)

    with pytest.raises(ValidationError, match="frozen"):
        limits.max_bytes = 200
