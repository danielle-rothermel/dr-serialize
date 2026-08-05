"""Canonical JSON text and bytes for validated Identity Documents."""

from __future__ import annotations

from dr_serialize.canonical import canonical_json, canonical_json_bytes
from dr_serialize.identity.document import (  # noqa: TC001 -- runtime hints
    IdentityDocument,
)


def canonical_identity_json(document: IdentityDocument) -> str:
    """Render Canonical Identity JSON Text for an Identity Document.

    Deterministic, compact, sorted-key UTF-8 JSON text of the complete
    three-field document. This pins the ``dr-serialize Canonical JSON Text
    profile v1`` used by :func:`dr_serialize.canonical.canonical_json`
    (``sort_keys=True``, ``separators=(",", ":")``, ``ensure_ascii=True``,
    ``allow_nan=False``), including preserved list order; it is NOT RFC 8785.
    Incompatible profiles require separately named APIs. The payload is
    already validated as a strict JSON value, so serialization cannot
    silently coerce a runtime value onto an identity.
    """
    return canonical_json(document.to_json_dict())


def canonical_identity_json_bytes(
    document: IdentityDocument,
    /,
) -> bytes:
    """Return the exact UTF-8 bytes of Canonical Identity JSON."""
    return canonical_json_bytes(document.to_json_dict())
