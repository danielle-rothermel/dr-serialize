"""Bounded bytes-first strict JSON decoding."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn, cast

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.errors import SerializationError
from dr_serialize.jsonable import Jsonable

_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_NON_FINITE_CONSTANTS = ("-Infinity", "Infinity", "NaN")
_WHITESPACE = frozenset(" \t\n\r")
_UNSET = object()


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


@dataclass(slots=True)
class _ArrayFrame:
    value: list[Jsonable]
    state: Literal["first_or_end", "value", "comma_or_end"] = "first_or_end"


@dataclass(slots=True)
class _ObjectFrame:
    value: dict[str, Jsonable]
    state: Literal[
        "first_key_or_end", "key", "colon", "value", "comma_or_end"
    ] = "first_key_or_end"
    key: str | None = field(default=None)


type _Frame = _ArrayFrame | _ObjectFrame


def decode_strict_json_bytes(
    data: bytes,
    /,
    *,
    max_bytes: int,
    max_depth: int,
) -> Jsonable:
    """Decode one bounded strict-JSON UTF-8 value without coercion.

    Structural parsing is iterative, so ``max_depth`` is enforced before
    nesting can consume the Python call stack. Diagnostics contain only
    bounded structural metadata and never echo the input.
    """
    _validate_limit("max_bytes", max_bytes)
    _validate_limit("max_depth", max_depth)
    if len(data) > max_bytes:
        raise JsonByteLimitError(size_bytes=len(data), max_bytes=max_bytes)
    try:
        text = data.decode(TEXT_ENCODING, errors="strict")
    except UnicodeDecodeError as error:
        invalid_utf8_offset = error.start
    else:
        invalid_utf8_offset = None
    if invalid_utf8_offset is not None:
        # Raise outside the except block so neither __cause__ nor __context__
        # retains the payload-bearing UnicodeDecodeError.
        raise InvalidUtf8Error(byte_offset=invalid_utf8_offset)
    if text.startswith("\ufeff"):
        _raise_syntax(text, 0, "byte-order mark is not permitted")
    return _StrictJsonParser(text, max_depth=max_depth).parse()


def _validate_limit(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


class _StrictJsonParser:
    def __init__(self, text: str, *, max_depth: int) -> None:
        self.text = text
        self.max_depth = max_depth
        self.index = 0
        self.root: object = _UNSET
        self.frames: list[_Frame] = []
        self.decoder = json.JSONDecoder()

    def parse(self) -> Jsonable:
        while True:
            self._skip_whitespace()
            if not self.frames and self.root is not _UNSET:
                if self.index != len(self.text):
                    _raise_syntax(self.text, self.index, "trailing data")
                # Every accepted token and container is constructed here as
                # a strict Jsonable value; no recursive validation pass is
                # needed after the iterative parse.
                return cast("Jsonable", self.root)
            if self.index == len(self.text):
                reason = (
                    "expected a JSON value"
                    if self.root is _UNSET
                    else "incomplete JSON value"
                )
                _raise_syntax(self.text, self.index, reason)
            if self.frames and self._advance_frame_punctuation():
                continue
            self._parse_value()

    def _skip_whitespace(self) -> None:
        while (
            self.index < len(self.text)
            and self.text[self.index] in _WHITESPACE
        ):
            self.index += 1

    def _advance_frame_punctuation(  # noqa: PLR0911, PLR0912 -- parser states
        self,
    ) -> bool:
        frame = self.frames[-1]
        character = self.text[self.index]
        if isinstance(frame, _ArrayFrame):
            if frame.state == "first_or_end" and character == "]":
                self.index += 1
                self.frames.pop()
                return True
            if frame.state == "comma_or_end":
                if character == "]":
                    self.index += 1
                    self.frames.pop()
                    return True
                if character == ",":
                    self.index += 1
                    frame.state = "value"
                    return True
                _raise_syntax(self.text, self.index, "expected ',' or ']'")
            return False

        if frame.state == "first_key_or_end" and character == "}":
            self.index += 1
            self.frames.pop()
            return True
        if frame.state == "comma_or_end":
            if character == "}":
                self.index += 1
                self.frames.pop()
                return True
            if character == ",":
                self.index += 1
                frame.state = "key"
                return True
            _raise_syntax(self.text, self.index, "expected ',' or '}'")
        if frame.state in ("first_key_or_end", "key"):
            if character != '"':
                _raise_syntax(self.text, self.index, "expected an object key")
            key_offset = self.index
            key = self._parse_string()
            if key in frame.value:
                raise DuplicateJsonKeyError(
                    byte_offset=_byte_offset(self.text, key_offset)
                )
            frame.key = key
            frame.state = "colon"
            return True
        if frame.state == "colon":
            if character != ":":
                _raise_syntax(self.text, self.index, "expected ':'")
            self.index += 1
            frame.state = "value"
            return True
        return False

    def _parse_value(self) -> None:  # noqa: PLR0912 -- JSON token forms
        if self.frames:
            frame = self.frames[-1]
            if isinstance(frame, _ArrayFrame):
                if frame.state not in ("first_or_end", "value"):
                    _raise_syntax(
                        self.text, self.index, "expected a JSON value"
                    )
            elif frame.state != "value":
                _raise_syntax(self.text, self.index, "expected a JSON value")

        start = self.index
        character = self.text[start]
        if character == '"':
            self._accept(self._parse_string())
            return
        if character == "[":
            value: list[Jsonable] = []
            self._accept(value)
            self._open(_ArrayFrame(value), start)
            return
        if character == "{":
            mapping: dict[str, Jsonable] = {}
            self._accept(mapping)
            self._open(_ObjectFrame(mapping), start)
            return
        for token in _NON_FINITE_CONSTANTS:
            if self.text.startswith(token, start):
                raise NonFiniteJsonNumberError(
                    byte_offset=_byte_offset(self.text, start)
                )
        for token, value in (("true", True), ("false", False), ("null", None)):
            if self.text.startswith(token, start):
                self.index += len(token)
                self._accept(value)
                return
        number_match = _NUMBER.match(self.text, start)
        if number_match is None:
            _raise_syntax(self.text, start, "expected a JSON value")
        token = number_match.group()
        self.index = number_match.end()
        number: int | float
        if "." in token or "e" in token.lower():
            number = float(token)
            if not math.isfinite(number):
                raise NonFiniteJsonNumberError(
                    byte_offset=_byte_offset(self.text, start)
                )
        else:
            try:
                integer = int(token)
            except ValueError:
                integer = None
            if integer is None:
                _raise_syntax(
                    self.text,
                    start,
                    "numeric value cannot be materialized",
                )
            number = integer
        self._accept(number)

    def _parse_string(self) -> str:
        start = self.index
        try:
            value, self.index = self.decoder.raw_decode(self.text, self.index)
        except json.JSONDecodeError:
            value = None
        if value is None:
            # Raise outside the except block so neither __cause__ nor
            # __context__ retains JSONDecodeError.doc.
            _raise_syntax(self.text, start, "malformed string")
        return cast("str", value)

    def _accept(self, value: Jsonable) -> None:
        if not self.frames:
            self.root = value
            return
        frame = self.frames[-1]
        if isinstance(frame, _ArrayFrame):
            frame.value.append(value)
            frame.state = "comma_or_end"
            return
        key = frame.key
        if key is None:
            _raise_syntax(self.text, self.index, "missing object key")
        frame.value[key] = value
        frame.key = None
        frame.state = "comma_or_end"

    def _open(self, frame: _Frame, offset: int) -> None:
        depth = len(self.frames) + 1
        if depth > self.max_depth:
            raise JsonDepthLimitError(
                depth=depth,
                max_depth=self.max_depth,
                byte_offset=_byte_offset(self.text, offset),
            )
        self.index += 1
        self.frames.append(frame)


def _byte_offset(text: str, character_offset: int) -> int:
    return len(text[:character_offset].encode(TEXT_ENCODING))


def _raise_syntax(
    text: str,
    character_offset: int,
    reason: str,
) -> NoReturn:
    line = text.count("\n", 0, character_offset) + 1
    line_start = text.rfind("\n", 0, character_offset)
    column = character_offset - line_start
    error = JsonSyntaxError(
        reason=reason,
        byte_offset=_byte_offset(text, character_offset),
        line=line,
        column=column,
    )
    raise error
