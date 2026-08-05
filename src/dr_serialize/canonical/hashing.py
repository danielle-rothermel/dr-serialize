"""SHA-256 hashing over canonical JSON text."""

from __future__ import annotations

import hashlib
from typing import overload

from dr_serialize._core.digests import SHA256_HEX_LENGTH, Sha256Digest
from dr_serialize._core.json_values import (  # noqa: TC001 -- runtime hints
    Jsonable,
)
from dr_serialize.canonical.json_text import canonical_json_bytes


@overload
def json_hash(value: Jsonable, *, length: None = None) -> Sha256Digest: ...


@overload
def json_hash(value: Jsonable, *, length: int) -> str: ...


def json_hash(
    value: Jsonable,
    *,
    length: int | None = None,
) -> Sha256Digest | str:
    hash_value = Sha256Digest(
        hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    )
    if length is None:
        return hash_value
    if length < 1 or length > SHA256_HEX_LENGTH:
        raise ValueError(
            f"hash length must be between 1 and "
            f"{SHA256_HEX_LENGTH}, got {length}"
        )
    return hash_value[:length]
