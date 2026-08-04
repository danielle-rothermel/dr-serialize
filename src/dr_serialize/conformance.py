"""Reusable immutable canonicalization conformance vectors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import UNIQUE, StrEnum, verify
from importlib.resources import files
from typing import Any

from dr_serialize.decoding import decode_strict_json_bytes
from dr_serialize.digests import Sha256Digest
from dr_serialize.errors import SerializationError

_CORPUS_RESOURCE = "data/conformance.json"
_CORPUS_MAX_DEPTH = 4
_VECTOR_FIELDS = frozenset(
    {
        "name",
        "lane",
        "input_json",
        "canonical_json",
        "canonical_utf8_hex",
        "sha256",
    }
)


@verify(UNIQUE)
class ConformanceLane(StrEnum):
    """Canonicalization lane exercised by a conformance vector.

    Never iterate over this enum to build serialized payloads; package data
    owns its explicit lane spellings.
    """

    CANONICAL_JSON = "canonical_json"
    IDENTITY_DOCUMENT = "identity_document"


@dataclass(frozen=True, slots=True)
class ConformanceVector:
    """One immutable input and its exact canonical outputs."""

    name: str
    lane: ConformanceLane
    input_json: str
    canonical_json: str
    canonical_bytes: bytes
    sha256: Sha256Digest


def load_conformance_corpus() -> tuple[ConformanceVector, ...]:
    """Load and validate the bundled canonicalization vectors."""
    raw = files("dr_serialize").joinpath(_CORPUS_RESOURCE).read_bytes()
    try:
        return _parse_corpus(raw)
    except (SerializationError, TypeError, ValueError) as error:
        raise RuntimeError("invalid bundled conformance corpus") from error


def _parse_corpus(raw: bytes) -> tuple[ConformanceVector, ...]:
    document = decode_strict_json_bytes(
        raw,
        max_bytes=len(raw),
        max_depth=_CORPUS_MAX_DEPTH,
    )
    if not isinstance(document, dict) or set(document) != {"vectors"}:
        raise ValueError("expected a vectors object")
    entries = document["vectors"]
    if not isinstance(entries, list):
        raise TypeError("vectors must be a list")
    return tuple(_load_vector(entry) for entry in entries)


def _load_vector(value: Any) -> ConformanceVector:
    if not isinstance(value, dict) or set(value) != _VECTOR_FIELDS:
        raise ValueError("invalid conformance vector shape")
    strings: dict[str, str] = {}
    for field_name in _VECTOR_FIELDS:
        field_value = value[field_name]
        if not isinstance(field_value, str):
            raise TypeError(f"{field_name} must be a string")
        strings[field_name] = field_value
    canonical_bytes = bytes.fromhex(strings["canonical_utf8_hex"])
    if canonical_bytes.decode("utf-8") != strings["canonical_json"]:
        raise ValueError("canonical bytes do not match canonical text")
    digest = Sha256Digest.parse(strings["sha256"])
    if hashlib.sha256(canonical_bytes).hexdigest() != digest:
        raise ValueError("digest does not match canonical bytes")
    return ConformanceVector(
        name=strings["name"],
        lane=ConformanceLane(strings["lane"]),
        input_json=strings["input_json"],
        canonical_json=strings["canonical_json"],
        canonical_bytes=canonical_bytes,
        sha256=digest,
    )
