"""JSON-safe serialization and canonical hashing, as deliberate lanes.

**Normalization lane** (policy, lossy, extensible):
:class:`Serializer` converts arbitrary Python values to diagnostic
normalized JSON value -- JSON-safe ``Jsonable`` data -- under explicit
:class:`SerializationLimits`, through an ordered, pluggable handler
chain (:mod:`dr_serialize.normalization`).

**Canonical JSON Text** (deterministic, policy-free): :func:`canonical_json`,
:func:`canonical_json_bytes`, and :func:`json_hash` turn finite strict JSON
values into stable canonical JSON text, exact bytes, and hashes under the
``dr-serialize Canonical JSON Text profile v1``
(:mod:`dr_serialize.canonical`).

**Strict JSON boundary** (policy-free): :func:`validate_strict_json` validates
in-memory values without coercion, while :func:`decode_strict_json_bytes`
parses bounded untrusted bytes.

**Identity lane** (strict, policy-free):
:class:`IdentityDocument`, :func:`canonical_identity_json`, and
:func:`identity_document_hash` implement the identity contract -- strict
JSON value validation, the exact three-field Identity Document,
its Canonical Identity JSON Text, and the full lowercase SHA-256 Identity Hash
(:mod:`dr_serialize.identity`). This lane never invokes the normalization
lane: a diagnostic normalized JSON value is potentially lossy and must not
feed identity hashing.

Normalization and canonical JSON text generation compose at the call site --
``json_hash(serializer.to_jsonable(x))`` -- so hash stability
never depends on handler policy. Typed errors live with their owning
functional areas over a shared diagnostic base. The
authoritative vocabulary and exported-name mapping live in
``.defs/terms.toml`` and its rendered terms reference.
"""

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
    preview_repr,
)
from dr_serialize._core.digests import Sha256Digest, Sha256DigestError
from dr_serialize._core.json_values import Jsonable
from dr_serialize._core.strict_json import (
    StrictJsonError,
    validate_strict_json,
)
from dr_serialize.canonical import (
    JsonEncodeError,
    canonical_json,
    canonical_json_bytes,
    canonical_sorted_values,
    json_hash,
)
from dr_serialize.decoding import (
    DuplicateJsonKeyError,
    InvalidUtf8Error,
    JsonByteLimitError,
    JsonDepthLimitError,
    JsonSyntaxError,
    NonFiniteJsonNumberError,
    StrictJsonDecodeError,
    decode_strict_json_bytes,
)
from dr_serialize.identity import (
    IDENTITY_DOCUMENT_FIELDS,
    IdentityDocument,
    IdentityDocumentError,
    build_identity_document,
    canonical_identity_json,
    canonical_identity_json_bytes,
    compute_identity_hash,
    identity_document_hash,
    identity_hash_prefix,
    validate_identity_document,
)
from dr_serialize.normalization import (
    POSTGRES_JSONB_MAX_BYTES,
    POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
    ConversionContext,
    JsonableHandle,
    JsonableHandler,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationLimits,
    Serializer,
    ValueTransformError,
    postgres_jsonb_limits,
)

__all__ = [
    "IDENTITY_DOCUMENT_FIELDS",
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "ConversionContext",
    "DuplicateJsonKeyError",
    "IdentityDocument",
    "IdentityDocumentError",
    "InvalidUtf8Error",
    "JsonByteLimitError",
    "JsonDepthLimitError",
    "JsonEncodeError",
    "JsonPath",
    "JsonSyntaxError",
    "Jsonable",
    "JsonableHandle",
    "JsonableHandler",
    "MaxDepthExceededError",
    "ModelDumpError",
    "NonFiniteJsonNumberError",
    "ObjectVarsSerializationError",
    "PayloadTooLargeError",
    "SerializationError",
    "SerializationLimits",
    "Serializer",
    "Sha256Digest",
    "Sha256DigestError",
    "StrictJsonDecodeError",
    "StrictJsonError",
    "ValueTransformError",
    "build_identity_document",
    "canonical_identity_json",
    "canonical_identity_json_bytes",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_sorted_values",
    "compute_identity_hash",
    "decode_strict_json_bytes",
    "detail_repr",
    "identity_document_hash",
    "identity_hash_prefix",
    "json_hash",
    "postgres_jsonb_limits",
    "preview_repr",
    "validate_identity_document",
    "validate_strict_json",
]
