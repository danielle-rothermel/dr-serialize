"""JSON-safe serialization and canonical hashing, as deliberate lanes.

**Normalization lane** (policy, lossy, extensible):
:class:`Serializer` converts arbitrary Python values to diagnostic
normalized JSON -- JSON-safe ``Jsonable`` data -- under explicit
:class:`SerializationLimits`, through an ordered, pluggable handler
chain (:mod:`dr_serialize.serialization`).

**Canonical JSON** (deterministic, policy-free): :func:`canonical_json`
and :func:`json_hash` turn already-JSON-safe values into stable
canonical text and hashes (:mod:`dr_serialize.canonical`).

**Identity lane** (strict, policy-free): :func:`validate_strict_json`,
:class:`IdentityDocument`, :func:`canonical_identity_json`, and
:func:`identity_document_hash` implement the identity contract -- strict
recursive JSON validation, the exact three-field Identity Document,
its Canonical Identity JSON, and the full lowercase SHA-256 Identity Hash
(:mod:`dr_serialize.identity`). This lane never invokes the normalization
lane: diagnostic normalized JSON is potentially lossy and must not feed
identity hashing.

Normalization and canonical JSON compose at the call site --
``json_hash(serializer.to_jsonable(x))`` -- so hash stability
never depends on handler policy. Typed errors for every lane live in
:mod:`dr_serialize.errors` and :mod:`dr_serialize.identity`. The
authoritative vocabulary for the identity contract -- terms, guarantees,
scope, and exported-name mapping -- lives in ``.defs/vocab.html``.
"""

from dr_serialize.canonical import canonical_json, json_hash
from dr_serialize.errors import (
    JsonEncodeError,
    JsonPath,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationError,
    ValueTransformError,
    detail_repr,
    preview_repr,
)
from dr_serialize.identity import (
    IDENTITY_DOCUMENT_FIELDS,
    IdentityDocument,
    IdentityDocumentError,
    StrictJsonError,
    build_identity_document,
    canonical_identity_json,
    compute_identity_hash,
    identity_document_hash,
    identity_hash_prefix,
    validate_identity_document,
    validate_strict_json,
)
from dr_serialize.jsonable import Jsonable
from dr_serialize.limits import (
    POSTGRES_JSONB_MAX_BYTES,
    POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
    SerializationLimits,
    postgres_jsonb_limits,
)
from dr_serialize.serialization import (
    ConversionContext,
    JsonableHandle,
    JsonableHandler,
    Serializer,
)

__all__ = [
    "IDENTITY_DOCUMENT_FIELDS",
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "ConversionContext",
    "IdentityDocument",
    "IdentityDocumentError",
    "JsonEncodeError",
    "JsonPath",
    "Jsonable",
    "JsonableHandle",
    "JsonableHandler",
    "MaxDepthExceededError",
    "ModelDumpError",
    "ObjectVarsSerializationError",
    "PayloadTooLargeError",
    "SerializationError",
    "SerializationLimits",
    "Serializer",
    "StrictJsonError",
    "ValueTransformError",
    "build_identity_document",
    "canonical_identity_json",
    "canonical_json",
    "compute_identity_hash",
    "detail_repr",
    "identity_document_hash",
    "identity_hash_prefix",
    "json_hash",
    "postgres_jsonb_limits",
    "preview_repr",
    "validate_identity_document",
    "validate_strict_json",
]
