"""Contract tests for the public reusable conformance corpus."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from dr_serialize import (
    ConformanceLane,
    Sha256Digest,
    canonical_identity_json,
    canonical_identity_json_bytes,
    canonical_json,
    canonical_json_bytes,
    decode_strict_json_bytes,
    identity_document_hash,
    json_hash,
    load_conformance_corpus,
    validate_identity_document,
)


def test_corpus_is_small_immutable_and_has_unique_names() -> None:
    corpus = load_conformance_corpus()
    assert isinstance(corpus, tuple)
    assert 1 <= len(corpus) <= 16
    assert len({vector.name for vector in corpus}) == len(corpus)
    assert {vector.lane for vector in corpus} == set(ConformanceLane)
    immutable_vector = cast("Any", corpus[0])
    with pytest.raises(FrozenInstanceError):
        immutable_vector.name = "changed"


def test_canonical_vectors_reproduce_every_output() -> None:
    vectors = [
        vector
        for vector in load_conformance_corpus()
        if vector.lane is ConformanceLane.CANONICAL_JSON
    ]
    for vector in vectors:
        data = vector.input_json.encode()
        value = decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=16,
        )
        assert canonical_json(value) == vector.canonical_json
        assert canonical_json_bytes(value) == vector.canonical_bytes
        assert json_hash(value) == vector.sha256
        assert isinstance(vector.sha256, Sha256Digest)


def test_identity_vectors_reproduce_every_output() -> None:
    vectors = [
        vector
        for vector in load_conformance_corpus()
        if vector.lane is ConformanceLane.IDENTITY_DOCUMENT
    ]
    for vector in vectors:
        data = vector.input_json.encode()
        value = decode_strict_json_bytes(
            data,
            max_bytes=len(data),
            max_depth=16,
        )
        document = validate_identity_document(cast("dict[Any, Any]", value))
        assert canonical_identity_json(document) == vector.canonical_json
        assert (
            canonical_identity_json_bytes(document) == vector.canonical_bytes
        )
        assert identity_document_hash(document) == vector.sha256
