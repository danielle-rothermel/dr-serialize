"""Canonical hashing and JSON-safe serialization.

Public surface: canonical JSON + digests (:mod:`dr_serialize.hashing`),
the instance-based conversion engine with pluggable handlers
(:mod:`dr_serialize.serialization`), explicit limits presets
(:mod:`dr_serialize.limits`), and the typed error taxonomy
(:mod:`dr_serialize.errors`).
"""

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
from dr_serialize.hashing import canonical_json, sha256_json_digest
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
