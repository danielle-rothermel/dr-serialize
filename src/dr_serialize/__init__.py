"""Canonical hashing and JSON-safe serialization.

Public surface: canonical JSON + digests (:mod:`dr_serialize.hashing`),
the conversion engine with pluggable handlers
(:mod:`dr_serialize.serialization`), explicit limits presets
(:mod:`dr_serialize.limits`), and the typed error taxonomy
(:mod:`dr_serialize.errors`).
"""

from dr_serialize.errors import (
    DEBUG_DETAIL_LIMIT,
    MESSAGE_PREVIEW,
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
from dr_serialize.hashing import (
    SHA256_HEX_DIGEST_LENGTH,
    canonical_json,
    sha256_json_digest,
)
from dr_serialize.limits import (
    POSTGRES_JSONB_MAX_BYTES,
    POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
    SerializationLimits,
    postgres_jsonb_limits,
)
from dr_serialize.serialization import (
    JsonableHandle,
    JsonableHandler,
    clear_registered_handlers,
    convert_value,
    register_handler,
    registered_handlers,
    to_jsonable,
    to_metadata_dict,
)

__all__ = [
    "DEBUG_DETAIL_LIMIT",
    "MESSAGE_PREVIEW",
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "SHA256_HEX_DIGEST_LENGTH",
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
    "ValueTransformError",
    "canonical_json",
    "clear_registered_handlers",
    "convert_value",
    "detail_repr",
    "postgres_jsonb_limits",
    "preview_repr",
    "register_handler",
    "registered_handlers",
    "sha256_json_digest",
    "to_jsonable",
    "to_metadata_dict",
]
