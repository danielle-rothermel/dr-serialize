"""JSON-safe serialization and canonical hashing, as two deliberate lanes.

**Normalization lane** (policy, lossy, extensible):
:class:`Serializer` converts arbitrary Python values to JSON-safe
``Jsonable`` data under explicit :class:`SerializationLimits`, through an
ordered, pluggable handler chain (:mod:`dr_serialize.serialization`).

**Identity lane** (deterministic, policy-free): :func:`canonical_json`
and :func:`sha256_json_digest` turn already-JSON-safe values into stable
canonical text and fingerprints (:mod:`dr_serialize.canonical`).

**Identity contract** (strict, policy-free): :func:`validate_finite_json`,
:class:`IdentityDocument`, :func:`canonical_identity_json`, and
:func:`identity_hash` implement the coordinated identity reset -- strict
recursive finite-JSON validation, the exact three-field Identity Document,
its Canonical Identity JSON, and the full lowercase SHA-256 Identity Hash
(:mod:`dr_serialize.identity`). This path never invokes the normalization
lane: diagnostic normalization is potentially lossy and must not feed
identity hashing.

The lanes compose at the call site --
``sha256_json_digest(serializer.to_jsonable(x))`` -- so digest stability
never depends on handler policy. Typed errors for every lane live in
:mod:`dr_serialize.errors` and :mod:`dr_serialize.identity`.
"""

from dr_serialize.canonical import canonical_json, sha256_json_digest
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
    FiniteJsonError,
    IdentityDocument,
    IdentityDocumentError,
    build_identity_document,
    canonical_identity_json,
    compute_identity_hash,
    identity_hash,
    identity_hash_prefix,
    validate_finite_json,
    validate_identity_document,
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
    "FiniteJsonError",
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
    "ValueTransformError",
    "build_identity_document",
    "canonical_identity_json",
    "canonical_json",
    "compute_identity_hash",
    "detail_repr",
    "identity_hash",
    "identity_hash_prefix",
    "postgres_jsonb_limits",
    "preview_repr",
    "sha256_json_digest",
    "validate_finite_json",
    "validate_identity_document",
]
