"""Policy-driven normalization of Python values into JSON-safe data."""

from dr_serialize.normalization.errors import (
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    ValueTransformError,
)
from dr_serialize.normalization.limits import (
    POSTGRES_JSONB_MAX_BYTES,
    POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
    SerializationLimits,
    postgres_jsonb_limits,
)
from dr_serialize.normalization.serializer import (
    ConversionContext,
    JsonableHandle,
    JsonableHandler,
    Serializer,
)

__all__ = [
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "ConversionContext",
    "JsonableHandle",
    "JsonableHandler",
    "MaxDepthExceededError",
    "ModelDumpError",
    "ObjectVarsSerializationError",
    "PayloadTooLargeError",
    "SerializationLimits",
    "Serializer",
    "ValueTransformError",
    "postgres_jsonb_limits",
]
