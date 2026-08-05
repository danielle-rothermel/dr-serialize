"""Typed failures raised by strict JSON byte decoding."""

from __future__ import annotations

from typing import Any

from dr_serialize._core.diagnostics import SerializationError


class StrictJsonDecodeError(SerializationError):
    """Base class for strict JSON byte-decoding failures."""

    path = ()


class JsonByteLimitError(StrictJsonDecodeError):
    """The encoded input exceeds its explicit byte limit."""

    def __init__(self, *, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        self.detail = "input exceeds the configured byte limit"
        super().__init__(
            f"JSON input is {size_bytes} bytes; limit is {max_bytes} bytes"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "size_bytes": self.size_bytes,
            "max_bytes": self.max_bytes,
        }


class JsonDepthLimitError(StrictJsonDecodeError):
    """The input nesting exceeds its explicit structural depth limit."""

    def __init__(
        self,
        *,
        depth: int,
        max_depth: int,
        byte_offset: int,
    ) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.byte_offset = byte_offset
        self.detail = "input exceeds the configured structural depth limit"
        super().__init__(
            f"JSON input reaches depth {depth}; limit is {max_depth}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "depth": self.depth,
            "max_depth": self.max_depth,
            "byte_offset": self.byte_offset,
        }


class InvalidUtf8Error(StrictJsonDecodeError):
    """The input is not valid UTF-8."""

    def __init__(self, *, byte_offset: int) -> None:
        self.byte_offset = byte_offset
        self.detail = "input is not valid UTF-8"
        super().__init__(f"invalid UTF-8 at byte offset {byte_offset}")

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "byte_offset": self.byte_offset,
        }


class JsonSyntaxError(StrictJsonDecodeError):
    """The input is malformed, incomplete, or contains trailing data."""

    def __init__(
        self,
        *,
        reason: str,
        byte_offset: int,
        line: int,
        column: int,
    ) -> None:
        self.reason = reason
        self.byte_offset = byte_offset
        self.line = line
        self.column = column
        self.detail = reason
        super().__init__(
            f"invalid JSON at line {line} column {column}: {reason}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "reason": self.reason,
            "byte_offset": self.byte_offset,
            "line": self.line,
            "column": self.column,
        }


class DuplicateJsonKeyError(StrictJsonDecodeError):
    """An object contains the same decoded key more than once."""

    def __init__(self, *, byte_offset: int) -> None:
        self.byte_offset = byte_offset
        self.detail = "object contains a duplicate key"
        super().__init__(
            f"duplicate JSON object key at byte offset {byte_offset}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "byte_offset": self.byte_offset,
        }


class NonFiniteJsonNumberError(StrictJsonDecodeError):
    """The input contains a non-finite numeric value."""

    def __init__(self, *, byte_offset: int) -> None:
        self.byte_offset = byte_offset
        self.detail = "input contains a non-finite number"
        super().__init__(
            f"non-finite JSON number at byte offset {byte_offset}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": [],
            "detail": self.detail,
            "byte_offset": self.byte_offset,
        }
