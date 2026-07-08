"""JSON-safe serialization and canonical hashing, as two deliberate lanes.

**Normalization lane** (policy, lossy, extensible):
:class:`Serializer` converts arbitrary Python values to JSON-safe
``Jsonable`` data under explicit :class:`SerializationLimits`, through an
ordered, pluggable handler chain (:mod:`dr_serialize.serialization`).

**Identity lane** (deterministic, policy-free): :func:`canonical_json`
and :func:`sha256_json_digest` turn already-JSON-safe values into stable
canonical text and fingerprints (:mod:`dr_serialize.canonical`).

The lanes compose at the call site --
``sha256_json_digest(serializer.to_jsonable(x))`` -- so digest stability
never depends on handler policy. Typed errors for both lanes live in
:mod:`dr_serialize.errors`.
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
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "ConversionContext",
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
    "canonical_json",
    "detail_repr",
    "postgres_jsonb_limits",
    "preview_repr",
    "sha256_json_digest",
]
