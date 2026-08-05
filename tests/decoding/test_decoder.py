"""Contract tests for bounded bytes-first strict JSON decoding."""

from __future__ import annotations

from typing import Any

import pytest

from dr_serialize import (
    DuplicateJsonKeyError,
    InvalidUtf8Error,
    JsonByteLimitError,
    JsonDepthLimitError,
    JsonSyntaxError,
    NonFiniteJsonNumberError,
    StrictJsonDecodeError,
    decode_strict_json_bytes,
    validate_strict_json,
)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"null", None),
        (b"true", True),
        (b"false", False),
        (b"0", 0),
        (b"-12", -12),
        (b"1.5", 1.5),
        ('"héllo"'.encode(), "héllo"),
        (b'"line\\nquoted\\t\\""', 'line\nquoted\t"'),
        (b"[]", []),
        (b"{}", {}),
        (b' [1,{"x":true},null] \n', [1, {"x": True}, None]),
    ],
)
def test_accepts_one_complete_strict_json_value(
    data: bytes, expected: Any
) -> None:
    decoded = decode_strict_json_bytes(
        data,
        max_bytes=len(data),
        max_depth=8,
    )
    assert decoded == expected
    assert validate_strict_json(decoded) is decoded


def test_byte_limit_exact_edge() -> None:
    data = b'{"x":1}'
    assert decode_strict_json_bytes(
        data, max_bytes=len(data), max_depth=1
    ) == {"x": 1}

    with pytest.raises(JsonByteLimitError) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data) - 1,
            max_depth=1,
        )
    assert exc_info.value.size_bytes == len(data)
    assert exc_info.value.max_bytes == len(data) - 1


def test_byte_limit_precedes_utf8_decoding() -> None:
    with pytest.raises(JsonByteLimitError):
        decode_strict_json_bytes(b"\xff\xff", max_bytes=1, max_depth=0)


def test_invalid_utf8_is_typed() -> None:
    with pytest.raises(InvalidUtf8Error) as exc_info:
        decode_strict_json_bytes(b'"\xff"', max_bytes=3, max_depth=0)
    assert exc_info.value.byte_offset == 1


def test_rejects_utf8_bom() -> None:
    data = b"\xef\xbb\xbf{}"
    with pytest.raises(JsonSyntaxError, match="byte-order mark"):
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=1)


@pytest.mark.parametrize(
    "data",
    [
        b'{"x":1,"x":2}',
        b'{"outer":{"x":1,"x":2}}',
        b'{"a":1,"\\u0061":2}',
    ],
)
def test_rejects_duplicate_decoded_object_keys(data: bytes) -> None:
    with pytest.raises(DuplicateJsonKeyError):
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=3)


@pytest.mark.parametrize(
    "data",
    [b"NaN", b"Infinity", b"-Infinity", b'{"x":1e400}'],
)
def test_rejects_non_finite_numbers(data: bytes) -> None:
    with pytest.raises(NonFiniteJsonNumberError):
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=2)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b" \n\t ",
        b"[",
        b'{"x"',
        b"[1,]",
        b'{"x":}',
        b"nul",
        b"01",
        b"1.",
        b"true false",
        b"{}[]",
        b"null trailing",
    ],
)
def test_rejects_malformed_trailing_or_multiple_values(data: bytes) -> None:
    with pytest.raises(JsonSyntaxError):
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=8)


def test_depth_limit_exact_edges() -> None:
    data = b'{"a":[{"b":null}]}'
    assert decode_strict_json_bytes(
        data,
        max_bytes=len(data),
        max_depth=3,
    ) == {"a": [{"b": None}]}

    with pytest.raises(JsonDepthLimitError) as exc_info:
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=2)
    assert exc_info.value.depth == 3
    assert exc_info.value.max_depth == 2


def test_scalar_is_depth_zero() -> None:
    assert decode_strict_json_bytes(b"1", max_bytes=1, max_depth=0) == 1
    with pytest.raises(JsonDepthLimitError):
        decode_strict_json_bytes(b"[]", max_bytes=2, max_depth=0)


def test_depth_rejection_does_not_depend_on_python_recursion() -> None:
    data = (b"[" * 2_000) + b"0" + (b"]" * 2_000)
    with pytest.raises(JsonDepthLimitError) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=64,
        )
    assert exc_info.value.depth == 65


def test_deep_value_with_matching_limit_does_not_recurse() -> None:
    depth = 2_000
    data = (b"[" * depth) + b"0" + (b"]" * depth)
    value = decode_strict_json_bytes(
        data,
        max_bytes=len(data),
        max_depth=depth,
    )
    for _ in range(depth):
        assert isinstance(value, list)
        assert len(value) == 1
        value = value[0]
    assert value == 0


def test_runtime_numeric_limit_is_translated_to_typed_error() -> None:
    data = b"1" * 5_000
    with pytest.raises(JsonSyntaxError, match="cannot be materialized"):
        decode_strict_json_bytes(data, max_bytes=len(data), max_depth=0)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_bytes", -1),
        ("max_bytes", True),
        ("max_depth", -1),
        ("max_depth", False),
    ],
)
def test_rejects_invalid_limits(name: str, value: Any) -> None:
    limits = {"max_bytes": 4, "max_depth": 0, name: value}
    with pytest.raises(ValueError, match=name):
        decode_strict_json_bytes(b"null", **limits)


@pytest.mark.parametrize(
    "error",
    [
        JsonByteLimitError(size_bytes=10_000_000, max_bytes=10),
        JsonDepthLimitError(depth=100, max_depth=10, byte_offset=99),
        InvalidUtf8Error(byte_offset=5),
        JsonSyntaxError(
            reason="trailing data", byte_offset=5, line=1, column=6
        ),
        DuplicateJsonKeyError(byte_offset=5),
        NonFiniteJsonNumberError(byte_offset=5),
    ],
)
def test_diagnostics_are_bounded_and_do_not_echo_input(
    error: StrictJsonDecodeError,
) -> None:
    secret = "secret-marker" * 10_000
    diagnostics = error.diagnostics()
    rendered = repr(diagnostics)
    assert secret not in rendered
    assert len(rendered) < 1_000


def test_large_adversarial_input_is_not_echoed_in_diagnostics() -> None:
    secret = "secret-marker" * 10_000
    data = ('"' + secret).encode()
    with pytest.raises(JsonSyntaxError) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=0,
        )
    rendered = repr(exc_info.value.diagnostics())
    assert secret not in rendered
    assert len(rendered) < 1_000
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_invalid_utf8_does_not_retain_payload_in_exception_chain() -> None:
    secret = b"secret-marker" * 10_000
    data = b'"' + secret + b'\xff"'
    with pytest.raises(InvalidUtf8Error) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=0,
        )
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
