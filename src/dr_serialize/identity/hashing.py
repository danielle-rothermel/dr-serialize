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
    """Return the full nominal SHA-256 digest of the document's canonical
    bytes.

    Use ``identity_hash_prefix`` only for display.
    """
    return Sha256Digest(
        hashlib.sha256(canonical_identity_json_bytes(document)).hexdigest()
    )


def compute_identity_hash(document: dict[Any, Any]) -> Sha256Digest:
    return identity_document_hash(validate_identity_document(document))


def identity_hash_prefix(hash_hex: Sha256Digest | str, length: int) -> str:
    """Return a display-only prefix of a validated full digest.

    Prefixes must not establish identity, equality, storage keys, or
    references.
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
