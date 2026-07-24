"""Identity lane: strict JSON, Identity Documents, the Identity Hash.

This module implements the identity lane of the identity contract; the
authoritative vocabulary -- terms, guarantees, scope, and exported-name
mapping -- lives in ``.defs/vocab.html``. The lane owns three things and
nothing else:

1. **Strict recursive JSON validation** -- accept only ``null``,
   ``bool``, ``str``, finite numbers, lists of accepted values, and dicts
   with string keys and accepted values. Every other runtime value, every
   non-string key, every non-finite number, and every reference cycle is
   rejected with a typed :class:`StrictJsonError` carrying a JsonPath-style
   location. There is no coercion, no custom serializer, and no lossy
   normalization on this path.

2. The exact three-field :class:`IdentityDocument`
   ``{schema, schema_version, payload}``. Missing or extra document fields
   are invalid. dr-serialize never selects payload fields; the owning
   domain passes a complete payload.

3. **Canonical Identity JSON** and the full **Identity Hash**: a
   deterministic compact sorted-key UTF-8 rendering of the complete
   validated document, and the full 64-character lowercase SHA-256 hex of
   its UTF-8 bytes.

dr-serialize selects no identity-bearing fields, no schema name, and no
schema version -- those belong to each owning domain.

This module is deliberately separate from the normalization lane
(:mod:`dr_serialize.serialization`). Diagnostic normalized JSON is
potentially lossy and MUST NOT feed identity hashing; nothing here calls
``Serializer.to_jsonable`` or any handler chain.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.canonical import SHA256_HEX_LENGTH
from dr_serialize.errors import SerializationError, detail_repr
from dr_serialize.jsonable import Jsonable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dr_serialize.errors import JsonPath

IDENTITY_DOCUMENT_FIELDS = ("schema", "schema_version", "payload")


class StrictJsonError(SerializationError):
    """A value is not strict JSON.

    Raised by :func:`validate_strict_json` (and therefore by document
    validation and hashing) when a value is not JSON, has a non-string
    object key, is a non-finite number, or forms a reference cycle. The
    ``path`` locates the exact offending leaf or key JsonPath-style.
    """

    def __init__(
        self,
        *,
        path: JsonPath,
        reason: str,
        type_name: str,
        detail: str,
    ) -> None:
        self.path = path
        self.reason = reason
        self.type_name = type_name
        self.detail = detail
        super().__init__(
            f"not strict JSON at path {path!r}: {reason} ({type_name})"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "reason": self.reason,
            "type_name": self.type_name,
        }


class IdentityDocumentError(SerializationError):
    """An Identity Document does not have the exact three-field shape.

    Raised by :func:`validate_identity_document` when the document is not a
    mapping, is missing a required field, carries an extra field, or has a
    field of the wrong type. Strict-JSON problems inside the payload raise
    :class:`StrictJsonError` instead.
    """

    def __init__(
        self,
        *,
        path: JsonPath,
        reason: str,
        detail: str,
    ) -> None:
        self.path = path
        self.reason = reason
        self.detail = detail
        super().__init__(
            f"invalid identity document at path {path!r}: {reason}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class IdentityDocument:
    """A validated, self-describing, versioned Identity Document.

    Construction itself validates (see :meth:`__post_init__`), so every
    ``IdentityDocument`` -- whether built via :func:`build_identity_document`,
    :func:`validate_identity_document`, or the exported constructor directly
    -- always holds a validated strict-JSON payload with the exact
    three-field shape. The owning domain chooses ``schema``,
    ``schema_version``, and the complete ``payload``; dr-serialize validates
    them.
    """

    schema: str
    schema_version: int
    payload: Jsonable

    def __post_init__(self) -> None:
        """Reject any document the validators would reject.

        The public constructor is exported, so it must enforce the same
        invariant as :func:`build_identity_document` /
        :func:`validate_identity_document`: ``schema`` is a string,
        ``schema_version`` is a real int (not bool), and ``payload`` is
        strict JSON. Without this, a directly constructed document
        with, for example, int/enum dict keys would be handed straight to
        ``json.dumps`` and have its keys silently coerced to strings,
        producing a valid-looking Identity Hash that collides with the
        string-keyed document. Validating here raises the typed
        :class:`IdentityDocumentError` / :class:`StrictJsonError` instead.
        """
        if not isinstance(self.schema, str):
            raise IdentityDocumentError(
                path=("schema",),
                reason="field must be a string",
                detail=detail_repr(self.schema),
            )
        # bool is a subclass of int; schema_version must be a real int.
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise IdentityDocumentError(
                path=("schema_version",),
                reason="field must be an integer",
                detail=detail_repr(self.schema_version),
            )
        validate_strict_json(self.payload, ("payload",))

    def to_json_dict(self) -> dict[str, Jsonable]:
        """Return the exact three-field document as a plain dict."""
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }


def validate_strict_json(
    value: Any,
    path: JsonPath = (),
    _seen: frozenset[int] = frozenset(),
) -> Jsonable:
    """Return ``value`` if it is strict JSON, else raise.

    Accepts, recursively: ``None``, ``bool``, ``int``, finite ``float``,
    ``str``, ``list`` of accepted values, and ``dict`` with ``str`` keys and
    accepted values. Rejects every other runtime type, non-string dict keys,
    non-finite numbers (``NaN``/``Inf``), and reference cycles, raising
    :class:`StrictJsonError` with the JsonPath-style ``path`` to the first
    offending value or key. No coercion or normalization is performed.
    """
    if value is None or isinstance(value, (bool, int, str)):
        # bool is a subclass of int; both are accepted JSON scalars.
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJsonError(
                path=path,
                reason="non-finite number",
                type_name="float",
                detail=detail_repr(value),
            )
        return value
    if isinstance(value, dict):
        if id(value) in _seen:
            raise StrictJsonError(
                path=path,
                reason="reference cycle",
                type_name="dict",
                detail=detail_repr(value),
            )
        seen = _seen | {id(value)}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrictJsonError(
                    path=path,
                    reason="non-string object key",
                    type_name=type(key).__name__,
                    detail=detail_repr(key),
                )
            validate_strict_json(item, (*path, key), seen)
        return value
    if isinstance(value, list):
        if id(value) in _seen:
            raise StrictJsonError(
                path=path,
                reason="reference cycle",
                type_name="list",
                detail=detail_repr(value),
            )
        seen = _seen | {id(value)}
        for index, item in enumerate(value):
            validate_strict_json(item, (*path, index), seen)
        return value
    raise StrictJsonError(
        path=path,
        reason="unsupported type",
        type_name=type(value).__name__,
        detail=detail_repr(value),
    )


def _require_field_type(
    document: Mapping[Any, Any],
    field: str,
    expected: type,
    type_label: str,
) -> Any:
    value = document[field]
    # bool is a subclass of int; schema_version must be a real int.
    if expected is int and isinstance(value, bool):
        raise IdentityDocumentError(
            path=(field,),
            reason=f"field must be {type_label}",
            detail=detail_repr(value),
        )
    if not isinstance(value, expected):
        raise IdentityDocumentError(
            path=(field,),
            reason=f"field must be {type_label}",
            detail=detail_repr(value),
        )
    return value


def validate_identity_document(
    document: Mapping[Any, Any],
) -> IdentityDocument:
    """Validate a mapping as an exact-shape Identity Document.

    Requires exactly the fields ``schema`` (str), ``schema_version`` (int,
    not bool), and ``payload`` (strict JSON). Missing fields, extra
    fields, and wrong field types raise :class:`IdentityDocumentError`;
    strict-JSON problems inside the payload raise :class:`StrictJsonError`
    with a ``("payload", ...)`` path.
    """
    if not isinstance(document, dict):
        raise IdentityDocumentError(
            path=(),
            reason="document must be an object",
            detail=detail_repr(document),
        )
    keys = set(document)
    expected = set(IDENTITY_DOCUMENT_FIELDS)
    missing = expected - keys
    if missing:
        raise IdentityDocumentError(
            path=(),
            reason=f"missing field(s): {sorted(missing)}",
            detail=detail_repr(sorted(keys)),
        )
    extra = keys - expected
    if extra:
        raise IdentityDocumentError(
            path=(),
            reason=f"unexpected field(s): {sorted(extra)}",
            detail=detail_repr(sorted(keys)),
        )
    schema = _require_field_type(document, "schema", str, "a string")
    schema_version = _require_field_type(
        document, "schema_version", int, "an integer"
    )
    payload = validate_strict_json(document["payload"], ("payload",))
    return IdentityDocument(
        schema=schema,
        schema_version=schema_version,
        payload=payload,
    )


def build_identity_document(
    *,
    schema: str,
    schema_version: int,
    payload: Any,
) -> IdentityDocument:
    """Validate and construct an :class:`IdentityDocument` from parts.

    A thin convenience over :func:`validate_identity_document` for callers
    that already hold the three fields separately. The owning domain still
    chooses every value; dr-serialize only validates.
    """
    return validate_identity_document(
        {
            "schema": schema,
            "schema_version": schema_version,
            "payload": payload,
        }
    )


def canonical_identity_json(document: IdentityDocument) -> str:
    """Render Canonical Identity JSON for a validated Identity Document.

    Deterministic, compact, sorted-key UTF-8 JSON text of the complete
    three-field document. This pins the same profile as
    :func:`dr_serialize.canonical.canonical_json`
    (``sort_keys=True``, ``separators=(",", ":")``, ``ensure_ascii=True``,
    ``allow_nan=False``); it is NOT RFC 8785. The payload is already
    validated strict JSON, so serialization cannot silently coerce a
    runtime value onto an identity.
    """
    return json.dumps(
        document.to_json_dict(),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def identity_document_hash(document: IdentityDocument) -> str:
    """Return the full Identity Hash of a validated Identity Document.

    The full 64-character lowercase SHA-256 hex of the Canonical Identity
    JSON UTF-8 bytes. There is deliberately no truncation or prefix
    parameter on this path; use :func:`identity_hash_prefix` for display.
    """
    return hashlib.sha256(
        canonical_identity_json(document).encode(TEXT_ENCODING)
    ).hexdigest()


def compute_identity_hash(document: Mapping[Any, Any]) -> str:
    """Validate a mapping and return its full Identity Hash.

    Convenience one-shot over :func:`validate_identity_document` and
    :func:`identity_document_hash` for callers holding a raw mapping.
    """
    return identity_document_hash(validate_identity_document(document))


def identity_hash_prefix(hash_hex: str, length: int) -> str:
    """Return a leading slice of an Identity Hash, for **display only**.

    This is a presentation helper and never establishes identity, equality,
    storage keys, or references. It operates on an already-computed full
    Identity Hash; it is intentionally not part of the hashing path. The
    input must be a full 64-character lowercase SHA-256 hex string.
    """
    if len(hash_hex) != SHA256_HEX_LENGTH:
        raise ValueError(
            f"expected a {SHA256_HEX_LENGTH}-character identity hash, "
            f"got length {len(hash_hex)}"
        )
    if length < 1 or length > SHA256_HEX_LENGTH:
        raise ValueError(
            f"display prefix length must be between 1 and "
            f"{SHA256_HEX_LENGTH}, got {length}"
        )
    return hash_hex[:length]
