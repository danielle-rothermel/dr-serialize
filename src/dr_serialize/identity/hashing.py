"""Full identity hashes and display-only prefixes."""

from __future__ import annotations

import hashlib
from typing import Any

from dr_serialize._core.digests import (
    SHA256_HEX_LENGTH,
    Sha256Digest,
    Sha256DigestError,
)
from dr_serialize.identity.canonical_json import canonical_identity_json_bytes
from dr_serialize.identity.document import (
    IdentityDocument,
    validate_identity_document,
)


def identity_document_hash(document: IdentityDocument) -> Sha256Digest:
    """Return the full Identity Hash of a validated Identity Document.

    The full 64-character lowercase SHA-256 hex of the Canonical Identity
    JSON Text's UTF-8 bytes. There is deliberately no truncation or prefix
    parameter on this path; use :func:`identity_hash_prefix` for display.
    """
    return Sha256Digest(
        hashlib.sha256(canonical_identity_json_bytes(document)).hexdigest()
    )


def compute_identity_hash(document: dict[Any, Any]) -> Sha256Digest:
    """Validate a dict and return its full Identity Hash.

    Convenience one-shot over :func:`validate_identity_document` and
    :func:`identity_document_hash` for callers holding a raw dict.
    """
    return identity_document_hash(validate_identity_document(document))


def identity_hash_prefix(hash_hex: Sha256Digest | str, length: int) -> str:
    """Return a leading slice of an Identity Hash, for **display only**.

    This is a presentation helper and never establishes identity, equality,
    storage keys, or references. It operates on an already-computed full
    Identity Hash; it is intentionally not part of the hashing path. The
    input must be a full 64-character lowercase SHA-256 hex string.
    """
    try:
        digest = Sha256Digest.parse(hash_hex)
    except Sha256DigestError as error:
        raise ValueError(f"invalid identity hash: {error.reason}") from error
    if length < 1 or length > SHA256_HEX_LENGTH:
        raise ValueError(
            f"display prefix length must be between 1 and "
            f"{SHA256_HEX_LENGTH}, got {length}"
        )
    return digest[:length]
