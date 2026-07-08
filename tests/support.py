"""Shared helpers and minimal fixtures for serialization contract tests."""

from __future__ import annotations

import json
from typing import Any

import pydantic

from dr_serialize import (
    SerializationError,
    SerializationLimits,
    Serializer,
    postgres_jsonb_limits,
)

_JSON_TYPES = (type(None), bool, int, float, str, list, dict)


def assert_json_dumps(value: Any) -> None:
    json.dumps(value, ensure_ascii=False)


def assert_only_json_types(value: Any) -> None:
    if isinstance(value, _JSON_TYPES):
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    msg = f"non-string dict key: {key!r}"
                    raise AssertionError(msg)  # noqa: TRY004
                assert_only_json_types(item)
        elif isinstance(value, list):
            for item in value:
                assert_only_json_types(item)
        return
    if isinstance(value, tuple):
        for item in value:
            assert_only_json_types(item)
        return
    msg = f"non-JSON type: {type(value).__name__}"
    raise AssertionError(msg)


def to_jsonable(value: Any, *, limits: SerializationLimits) -> Any:
    """Function-style adapter over Serializer for terse test call sites."""
    return Serializer(limits=limits).to_jsonable(value)


def assert_to_jsonable(
    value: Any,
    *,
    limits: SerializationLimits | None = None,
) -> Any:
    result = to_jsonable(value, limits=limits or postgres_jsonb_limits())
    assert_json_dumps(result)
    assert_only_json_types(result)
    return result


def assert_diagnostics(
    exc: SerializationError,
    required_keys: set[str],
    **expected_fields: Any,
) -> dict[str, Any]:
    diagnostics = exc.diagnostics()
    assert set(diagnostics) >= required_keys
    for key, expected in expected_fields.items():
        assert diagnostics[key] == expected, (
            f"diagnostics[{key!r}]: {diagnostics[key]!r} != {expected!r}"
        )
    return diagnostics


def nested_list(depth: int, leaf: str = "x") -> list[Any]:
    value: Any = leaf
    for _ in range(depth):
        value = [value]
    return value


def large_payload(char_count: int) -> dict[str, str]:
    return {"blob": "a" * char_count}


class OkModel(pydantic.BaseModel):
    name: str
    count: int


class SerializedNameModel(pydantic.BaseModel):
    name: str

    @pydantic.field_serializer("name")
    def serialize_name(self, value: str) -> str:
        return value.upper()


def ok_pydantic_model() -> OkModel:
    return OkModel(name="n", count=1)


class BadModel(pydantic.BaseModel):
    x: object


def bad_pydantic_model() -> BadModel:
    return BadModel(x=object())


class SimpleObject:
    def __init__(self) -> None:
        self.a = 1
        self.label = "test"
