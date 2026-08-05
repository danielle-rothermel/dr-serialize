"""Canonical JSON text, value ordering, and hashing."""

from dr_serialize.canonical.errors import JsonEncodeError
from dr_serialize.canonical.hashing import json_hash
from dr_serialize.canonical.json_text import (
    canonical_json,
    canonical_json_bytes,
)
from dr_serialize.canonical.profile import (
    CANONICAL_JSON_MAX_CONTAINER_DEPTH,
    CANONICAL_JSON_MAX_INTEGER_DIGITS,
)
from dr_serialize.canonical.value_ordering import canonical_sorted_values

__all__ = [
    "CANONICAL_JSON_MAX_CONTAINER_DEPTH",
    "CANONICAL_JSON_MAX_INTEGER_DIGITS",
    "JsonEncodeError",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_sorted_values",
    "json_hash",
]
