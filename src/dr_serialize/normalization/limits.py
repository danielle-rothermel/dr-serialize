from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

# Policy approximation of PostgreSQL's documented 1 GB field limit.
POSTGRES_JSONB_MAX_BYTES = 1 << 30

# Policy reserve for JSON-text-to-JSONB expansion; PostgreSQL defines no
# fixed expansion ratio.
POSTGRES_JSONB_TEXT_TO_BINARY_OVERHEAD_RATIO = 0.25

POSTGRES_JSONB_PAYLOAD_MAX_BYTES = POSTGRES_JSONB_MAX_BYTES - int(
    POSTGRES_JSONB_MAX_BYTES * POSTGRES_JSONB_TEXT_TO_BINARY_OVERHEAD_RATIO
)

# Library policy guard against runaway nesting.
DEFAULT_MAX_DEPTH = 100


class SerializationLimits(BaseModel):
    """Validated normalization depth and size bounds.

    ``hard_max_bytes`` records the storage ceiling reported in diagnostics;
    when omitted, diagnostics use ``max_bytes``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_depth: Annotated[StrictInt, Field(ge=0)] = DEFAULT_MAX_DEPTH
    max_bytes: Annotated[StrictInt, Field(ge=0)]
    hard_max_bytes: Annotated[StrictInt, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def validate_byte_limits(self) -> Self:
        if (
            self.hard_max_bytes is not None
            and self.max_bytes > self.hard_max_bytes
        ):
            raise ValueError("max_bytes must not exceed hard_max_bytes")
        return self

    @property
    def effective_hard_max_bytes(self) -> int:
        if self.hard_max_bytes is not None:
            return self.hard_max_bytes
        return self.max_bytes


def postgres_jsonb_limits(
    max_bytes: int = POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
) -> SerializationLimits:
    """Return the Postgres JSONB preset.

    It has a configurable payload ceiling up to the Postgres hard maximum.
    """
    return SerializationLimits(
        max_depth=DEFAULT_MAX_DEPTH,
        max_bytes=max_bytes,
        hard_max_bytes=POSTGRES_JSONB_MAX_BYTES,
    )
