"""Normalization limits as explicit, injectable configuration.

Postgres JSONB ships as *a* preset, not *the* truth: consumers with other
storage ceilings (or none) construct their own ``SerializationLimits``.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

# PostgreSQL jsonb/text per-value maximum (~1 GiB; see PG MaxAllocSize).
POSTGRES_JSONB_MAX_BYTES = 1 << 30  # 1_073_741_824

# Empirical headroom for compact JSON text → jsonb binary expansion.
# PG does not define this; 25% is a conservative upper bound for structured
# telemetry JSON (see depesz.com JSON vs JSONB sizing benchmarks).
POSTGRES_JSONB_TEXT_TO_BINARY_OVERHEAD_RATIO = 0.25

POSTGRES_JSONB_PAYLOAD_MAX_BYTES = POSTGRES_JSONB_MAX_BYTES - int(
    POSTGRES_JSONB_MAX_BYTES * POSTGRES_JSONB_TEXT_TO_BINARY_OVERHEAD_RATIO
)  # 805_306_368 bytes (~768 MiB)

# Practical JSON nesting guard. Postgres has no fixed cap, but 100 matches
# common JSON storage limits and catches runaway recursion.
DEFAULT_MAX_DEPTH = 100


class SerializationLimits(BaseModel):
    """Depth and size ceilings enforced by ``to_jsonable``.

    All configured limits are non-negative. When ``hard_max_bytes`` is
    present, ``max_bytes`` cannot exceed it.

    ``hard_max_bytes`` is the storage backend's absolute per-value ceiling,
    reported in oversize diagnostics alongside the configured ``max_bytes``;
    when omitted it defaults to ``max_bytes``.
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
    """Postgres JSONB preset, optionally with a tighter payload ceiling."""
    return SerializationLimits(
        max_depth=DEFAULT_MAX_DEPTH,
        max_bytes=max_bytes,
        hard_max_bytes=POSTGRES_JSONB_MAX_BYTES,
    )
