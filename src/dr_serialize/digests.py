"""Validated full SHA-256 digest values."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic_core import core_schema

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema

SHA256_HEX_LENGTH = 64
_LOWERCASE_HEX = frozenset("0123456789abcdef")


class Sha256DigestError(ValueError):
    """A value is not a full lowercase SHA-256 digest."""

    def __init__(self, *, reason: str, length: int | None) -> None:
        self.reason = reason
        self.length = length
        super().__init__(f"invalid SHA-256 digest: {reason}")


class Sha256Digest(str):
    """A full 64-character lowercase hexadecimal SHA-256 digest."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise Sha256DigestError(
                reason="value must be a string",
                length=None,
            )
        if len(value) != SHA256_HEX_LENGTH:
            raise Sha256DigestError(
                reason=f"expected {SHA256_HEX_LENGTH} characters",
                length=len(value),
            )
        if any(character not in _LOWERCASE_HEX for character in value):
            raise Sha256DigestError(
                reason="value must contain only lowercase hexadecimal",
                length=len(value),
            )
        return super().__new__(cls, value)

    @classmethod
    def parse(cls, value: str, /) -> Self:
        """Validate ``value`` and return its nominal digest value."""
        return cls(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """Provide strict validation and serialization for Pydantic fields."""
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(
                strict=True,
                min_length=SHA256_HEX_LENGTH,
                max_length=SHA256_HEX_LENGTH,
                pattern=r"^[0-9a-f]{64}$",
            ),
        )
