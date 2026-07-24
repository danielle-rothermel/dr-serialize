"""Canonical JSON: deterministic text and hashes for JSON-safe values.

Deterministic and policy-free: no handlers, no limits, no normalization.
These general-purpose utilities consume the ``Jsonable`` values the
conversion engine (:mod:`dr_serialize.serialization`) produces; to
fingerprint an arbitrary object, compose with the normalization lane
explicitly::

    hash_value = json_hash(serializer.to_jsonable(value))

They are distinct from the identity lane (:mod:`dr_serialize.identity`),
which restricts hashing to validated Identity Documents.

Canonical text is the contract-bearer: hash stability derives from
canonical-text stability, and consumers pin both with golden tests.
"""

from __future__ import annotations

import hashlib
import json

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.errors import JsonEncodeError, detail_repr, preview_repr
from dr_serialize.jsonable import Jsonable, find_json_failure

SHA256_HEX_LENGTH = 64


def canonical_json(value: Jsonable) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        failure_path, leaf = find_json_failure(
            value,
            reject_non_finite=True,
        ) or ((), value)
        raise JsonEncodeError(
            path=failure_path,
            type_name=type(leaf).__name__,
            detail=detail_repr(leaf),
            underlying=error,
            value_preview=preview_repr(value),
        ) from error


def json_hash(
    value: Jsonable,
    *,
    length: int | None = None,
) -> str:
    hash_value = hashlib.sha256(
        canonical_json(value).encode(TEXT_ENCODING)
    ).hexdigest()
    if length is None:
        return hash_value
    if length < 1 or length > SHA256_HEX_LENGTH:
        raise ValueError(
            f"hash length must be between 1 and "
            f"{SHA256_HEX_LENGTH}, got {length}"
        )
    return hash_value[:length]
