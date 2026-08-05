from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dr_serialize import (
    CANONICAL_JSON_MAX_CONTAINER_DEPTH,
    CANONICAL_JSON_MAX_INTEGER_DIGITS,
    Jsonable,
    JsonEncodeError,
    canonical_json,
)


class _MisleadingAbsInt(int):
    def __abs__(self) -> int:
        return 0


class _RaisingAbsInt(int):
    def __abs__(self) -> int:
        raise RuntimeError("absolute value failed")


def _nested_list(depth: int, leaf: Jsonable = 0) -> Jsonable:
    value = leaf
    for _ in range(depth):
        value = [value]
    return value


def test_profile_limits_are_public_and_frozen_at_v1_values() -> None:
    import dr_serialize
    import dr_serialize.canonical

    assert CANONICAL_JSON_MAX_CONTAINER_DEPTH == 200
    assert CANONICAL_JSON_MAX_INTEGER_DIGITS == 640
    assert (
        dr_serialize.canonical.CANONICAL_JSON_MAX_CONTAINER_DEPTH
        == CANONICAL_JSON_MAX_CONTAINER_DEPTH
    )
    assert (
        dr_serialize.canonical.CANONICAL_JSON_MAX_INTEGER_DIGITS
        == CANONICAL_JSON_MAX_INTEGER_DIGITS
    )
    assert "CANONICAL_JSON_MAX_CONTAINER_DEPTH" in dr_serialize.__all__
    assert "CANONICAL_JSON_MAX_INTEGER_DIGITS" in dr_serialize.__all__
    assert (
        "CANONICAL_JSON_MAX_CONTAINER_DEPTH" in dr_serialize.canonical.__all__
    )
    assert (
        "CANONICAL_JSON_MAX_INTEGER_DIGITS" in dr_serialize.canonical.__all__
    )


def test_profile_accepts_exact_maximum_container_depth() -> None:
    value = _nested_list(CANONICAL_JSON_MAX_CONTAINER_DEPTH)

    assert canonical_json(value) == (
        f"{'[' * CANONICAL_JSON_MAX_CONTAINER_DEPTH}0"
        f"{']' * CANONICAL_JSON_MAX_CONTAINER_DEPTH}"
    )


def test_profile_rejects_first_container_beyond_maximum_depth() -> None:
    value = _nested_list(CANONICAL_JSON_MAX_CONTAINER_DEPTH + 1)

    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(value)

    error = exc_info.value
    assert error.path == (0,) * 200
    assert error.type_name == "list"
    assert error.detail == "container depth 201 exceeds maximum 200"
    assert isinstance(error.underlying, ValueError)


@pytest.mark.parametrize("sign", [1, -1])
def test_profile_accepts_exact_maximum_integer_digits(sign: int) -> None:
    accepted_exponent = CANONICAL_JSON_MAX_INTEGER_DIGITS - 1
    value = sign * 10**accepted_exponent
    expected = ("-" if sign < 0 else "") + "1" + "0" * accepted_exponent

    assert canonical_json(value) == expected


@pytest.mark.parametrize("sign", [1, -1])
def test_profile_rejects_first_integer_beyond_maximum_digits(
    sign: int,
) -> None:
    value: Jsonable = {
        "n": sign * 10**CANONICAL_JSON_MAX_INTEGER_DIGITS,
    }

    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(value)

    error = exc_info.value
    assert error.path == ("n",)
    assert error.type_name == "int"
    assert error.detail == "integer exceeds maximum 640 decimal digits"
    assert isinstance(error.underlying, ValueError)


@pytest.mark.parametrize(
    "value_type",
    [_MisleadingAbsInt, _RaisingAbsInt],
)
def test_profile_bound_cannot_be_bypassed_by_int_subclass(
    value_type: type[int],
) -> None:
    value = value_type(10**CANONICAL_JSON_MAX_INTEGER_DIGITS)

    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(value)

    assert exc_info.value.path == ()
    assert (
        exc_info.value.detail == "integer exceeds maximum 640 decimal digits"
    )


@pytest.mark.subprocess
@pytest.mark.parametrize("interpreter_limit", ["640", "0"])
def test_profile_is_independent_of_interpreter_integer_limit(
    interpreter_limit: str,
) -> None:
    code = """
from dr_serialize import JsonEncodeError, canonical_json

accepted = canonical_json(10**639)
assert accepted == "1" + "0" * 639
try:
    canonical_json(10**640)
except JsonEncodeError as error:
    assert error.detail == "integer exceeds maximum 640 decimal digits"
else:
    raise AssertionError("641-digit integer was accepted")
"""
    env = os.environ.copy()
    env["PYTHONINTMAXSTRDIGITS"] = interpreter_limit
    source_root = Path(__file__).parents[2] / "src"
    env["PYTHONPATH"] = str(source_root)

    subprocess.run(  # noqa: S603 -- fixed interpreter and in-repo code
        [sys.executable, "-c", code],
        check=True,
        env=env,
        timeout=10,
    )
