"""Canonical JSON Text: deterministic text and hashes for strict JSON values.

The ``dr-serialize Canonical JSON Text profile v1`` sorts object keys,
preserves list order, uses compact separators, escapes non-ASCII characters,
and accepts only finite strict JSON input. It is not RFC 8785. An incompatible
profile requires a separately named API rather than a flag or version
parameter on these functions.

The profile is deterministic and policy-free: no handlers, no limits, no
normalization. These general-purpose utilities consume ``Jsonable`` values;
to fingerprint an arbitrary object, compose with the normalization lane
explicitly::

    hash_value = json_hash(serializer.to_jsonable(value))

They are distinct from the identity lane (:mod:`dr_serialize.identity`),
which restricts hashing to validated Identity Documents.

Canonical JSON text is the contract-bearer: hash stability derives from
canonical JSON text stability, and consumers pin both with golden tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import overload

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.digests import SHA256_HEX_LENGTH, Sha256Digest
from dr_serialize.errors import JsonEncodeError, detail_repr, preview_repr
from dr_serialize.jsonable import Jsonable, _find_strict_json_failure


def canonical_json(value: Jsonable) -> str:
    """Render ``value`` using dr-serialize Canonical JSON Text profile v1.

    Runtime validation rejects values outside strict ``Jsonable`` before
    encoding. Unsupported types, non-string object keys, and reference cycles
    carry an underlying :class:`TypeError`; non-finite numbers carry an
    underlying :class:`ValueError`.
    """
    failure = _find_strict_json_failure(value)
    if failure is not None:
        failure_path, leaf, reason = failure
        underlying: TypeError | ValueError
        if reason == "non-finite number":
            underlying = ValueError(reason)
        else:
            underlying = TypeError(reason)
        error = JsonEncodeError(
            path=failure_path,
            type_name=type(leaf).__name__,
            detail=detail_repr(leaf),
            underlying=underlying,
            value_preview=preview_repr(value),
        )
        raise error from underlying

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise JsonEncodeError(
            path=(),
            type_name=type(value).__name__,
            detail=detail_repr(value),
            underlying=error,
            value_preview=preview_repr(value),
        ) from error


def canonical_json_bytes(value: Jsonable, /) -> bytes:
    """Return the exact UTF-8 bytes of :func:`canonical_json`."""
    return canonical_json(value).encode(TEXT_ENCODING)


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
