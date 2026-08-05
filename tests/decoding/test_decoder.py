from __future__ import annotations

from dataclasses import dataclass
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

_SENSITIVE_MARKER = "decoder-sensitive-marker"


@dataclass(frozen=True, slots=True)
class _PositionCase:
    data: bytes
    error_type: type[StrictJsonDecodeError]
    detail: str
    byte_offset: int
    line: int | None = None
    column: int | None = None
    max_depth: int = 8


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
    "case",
    [
        pytest.param(
            _PositionCase(
                data='[\n  "é" true]'.encode(),
                error_type=JsonSyntaxError,
                detail="expected ',' or ']'",
                byte_offset=9,
                line=2,
                column=7,
            ),
            id="missing-array-comma",
        ),
        pytest.param(
            _PositionCase(
                data='{\n  "é": 1 "b": 2}'.encode(),
                error_type=JsonSyntaxError,
                detail="expected ',' or '}'",
                byte_offset=12,
                line=2,
                column=10,
            ),
            id="missing-object-comma",
        ),
        pytest.param(
            _PositionCase(
                data='{"é": 1,\n  2: 3}'.encode(),
                error_type=JsonSyntaxError,
                detail="expected an object key",
                byte_offset=12,
                line=2,
                column=3,
            ),
            id="non-string-object-key",
        ),
        pytest.param(
            _PositionCase(
                data='{"é"\n  1}'.encode(),
                error_type=JsonSyntaxError,
                detail="expected ':'",
                byte_offset=8,
                line=2,
                column=3,
            ),
            id="missing-colon",
        ),
        pytest.param(
            _PositionCase(
                data='[\n  "é\\x"]'.encode(),
                error_type=JsonSyntaxError,
                detail="malformed string",
                byte_offset=4,
                line=2,
                column=3,
            ),
            id="malformed-string",
        ),
        pytest.param(
            _PositionCase(
                data='{"é": 1}\n  false'.encode(),
                error_type=JsonSyntaxError,
                detail="trailing data",
                byte_offset=12,
                line=2,
                column=3,
            ),
            id="trailing-data",
        ),
        pytest.param(
            _PositionCase(
                data='{\n  "é": 1,\n  "\\u00e9": 2}'.encode(),
                error_type=DuplicateJsonKeyError,
                detail="object contains a duplicate key",
                byte_offset=15,
            ),
            id="decoded-duplicate-key",
        ),
        pytest.param(
            _PositionCase(
                data='{\n  "é": [0]}'.encode(),
                error_type=JsonDepthLimitError,
                detail="input exceeds the configured structural depth limit",
                byte_offset=10,
                max_depth=1,
            ),
            id="depth-overflow",
        ),
        pytest.param(
            _PositionCase(
                data='{\n  "é": 1e400}'.encode(),
                error_type=NonFiniteJsonNumberError,
                detail="input contains a non-finite number",
                byte_offset=10,
            ),
            id="numeric-overflow",
        ),
        pytest.param(
            _PositionCase(
                data='{\n  "é": "'.encode() + b'\xff"}',
                error_type=InvalidUtf8Error,
                detail="input is not valid UTF-8",
                byte_offset=11,
            ),
            id="invalid-utf8",
        ),
    ],
)
def test_errors_report_structured_positions(case: _PositionCase) -> None:
    with pytest.raises(StrictJsonDecodeError) as exc_info:
        decode_strict_json_bytes(
            case.data,
            max_bytes=len(case.data),
            max_depth=case.max_depth,
        )

    error = exc_info.value
    diagnostics = error.diagnostics()
    assert type(error) is case.error_type
    assert error.detail == case.detail
    assert diagnostics["detail"] == case.detail
    assert diagnostics["byte_offset"] == case.byte_offset
    if case.line is None:
        assert "line" not in diagnostics
        assert "column" not in diagnostics
        assert "reason" not in diagnostics
    else:
        assert isinstance(error, JsonSyntaxError)
        assert error.reason == case.detail
        assert error.line == case.line
        assert error.column == case.column
        assert diagnostics["reason"] == case.detail
        assert diagnostics["line"] == case.line
        assert diagnostics["column"] == case.column


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
    ("error", "expected"),
    [
        (
            JsonByteLimitError(size_bytes=10_000_000, max_bytes=10),
            {
                "path": [],
                "detail": "input exceeds the configured byte limit",
                "size_bytes": 10_000_000,
                "max_bytes": 10,
            },
        ),
        (
            JsonDepthLimitError(depth=100, max_depth=10, byte_offset=99),
            {
                "path": [],
                "detail": (
                    "input exceeds the configured structural depth limit"
                ),
                "depth": 100,
                "max_depth": 10,
                "byte_offset": 99,
            },
        ),
        (
            InvalidUtf8Error(byte_offset=5),
            {
                "path": [],
                "detail": "input is not valid UTF-8",
                "byte_offset": 5,
            },
        ),
        (
            JsonSyntaxError(
                reason="trailing data", byte_offset=5, line=1, column=6
            ),
            {
                "path": [],
                "detail": "trailing data",
                "reason": "trailing data",
                "byte_offset": 5,
                "line": 1,
                "column": 6,
            },
        ),
        (
            DuplicateJsonKeyError(byte_offset=5),
            {
                "path": [],
                "detail": "object contains a duplicate key",
                "byte_offset": 5,
            },
        ),
        (
            NonFiniteJsonNumberError(byte_offset=5),
            {
                "path": [],
                "detail": "input contains a non-finite number",
                "byte_offset": 5,
            },
        ),
    ],
)
def test_error_constructor_diagnostics_shape_is_exact(
    error: StrictJsonDecodeError,
    expected: dict[str, Any],
) -> None:
    assert error.diagnostics() == expected


@pytest.mark.parametrize(
    ("data", "max_bytes", "max_depth", "error_type"),
    [
        pytest.param(
            _SENSITIVE_MARKER.encode(),
            0,
            0,
            JsonByteLimitError,
            id="byte-limit",
        ),
        pytest.param(
            f'{{"{_SENSITIVE_MARKER}":[]}}'.encode(),
            None,
            1,
            JsonDepthLimitError,
            id="depth-limit",
        ),
        pytest.param(
            b'"' + _SENSITIVE_MARKER.encode() + b'\xff"',
            None,
            0,
            InvalidUtf8Error,
            id="invalid-utf8",
        ),
        pytest.param(
            f'"{_SENSITIVE_MARKER}'.encode(),
            None,
            0,
            JsonSyntaxError,
            id="syntax",
        ),
        pytest.param(
            (f'{{"{_SENSITIVE_MARKER}":1,"{_SENSITIVE_MARKER}":2}}').encode(),
            None,
            1,
            DuplicateJsonKeyError,
            id="duplicate-key",
        ),
        pytest.param(
            f'{{"{_SENSITIVE_MARKER}":NaN}}'.encode(),
            None,
            1,
            NonFiniteJsonNumberError,
            id="non-finite-number",
        ),
    ],
)
def test_decoder_error_message_diagnostics_and_chain_exclude_secret(
    data: bytes,
    max_bytes: int | None,
    max_depth: int,
    error_type: type[StrictJsonDecodeError],
) -> None:
    with pytest.raises(StrictJsonDecodeError) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data) if max_bytes is None else max_bytes,
            max_depth=max_depth,
        )

    error = exc_info.value
    message = str(error)
    diagnostics = error.diagnostics()
    assert type(error) is error_type
    assert _SENSITIVE_MARKER not in message
    assert len(message) < 256
    assert 1 <= len(diagnostics) <= 6
    for key, value in diagnostics.items():
        assert len(key) < 32
        if isinstance(value, str):
            assert _SENSITIVE_MARKER not in value
            assert len(value) < 128
        elif isinstance(value, list):
            assert value == []
        else:
            assert isinstance(value, int)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_large_adversarial_input_is_not_echoed_in_diagnostics() -> None:
    data = ('"' + (_SENSITIVE_MARKER * 10_000)).encode()
    with pytest.raises(JsonSyntaxError) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=0,
        )
    rendered = repr(exc_info.value.diagnostics())
    assert _SENSITIVE_MARKER not in rendered
    assert len(rendered) < 1_000
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_invalid_utf8_does_not_retain_payload_in_exception_chain() -> None:
    data = b'"' + (_SENSITIVE_MARKER.encode() * 10_000) + b'\xff"'
    with pytest.raises(InvalidUtf8Error) as exc_info:
        decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=0,
        )
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
