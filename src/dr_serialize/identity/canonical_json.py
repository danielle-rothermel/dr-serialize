from __future__ import annotations

from dr_serialize.canonical import canonical_json, canonical_json_bytes
from dr_serialize.identity.document import (  # noqa: TC001 -- runtime hints
    IdentityDocument,
)


def canonical_identity_json(document: IdentityDocument) -> str:
    """Render the complete document with Canonical JSON Text profile v1.

    This project-owned profile is not RFC 8785; incompatible profiles require
    separately named APIs.
    """
    return canonical_json(document.to_json_dict())


def canonical_identity_json_bytes(
    document: IdentityDocument,
    /,
) -> bytes:
    return canonical_json_bytes(document.to_json_dict())
