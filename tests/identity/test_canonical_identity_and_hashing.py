"""Contract tests for canonical identity rendering and hashing.

The golden fixture in ``tests/fixtures/identity_golden.json`` is committed
for reuse by other repositories. Byte-identical canonical JSON text and
identical hashes are the cross-repository acceptance gate.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from dr_serialize import (
    IdentityDocument,
    Jsonable,
    Sha256Digest,
    build_identity_document,
    canonical_identity_json,
    canonical_identity_json_bytes,
    compute_identity_hash,
    identity_document_hash,
    identity_hash_prefix,
    validate_identity_document,
)
from dr_serialize._core.digests import SHA256_HEX_LENGTH

GOLDEN_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "identity_golden.json"
)


# --------------------------------------------------------------------------
# Canonical Identity JSON Text and Identity Hash
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("renderer", "return_type"),
    [
        (canonical_identity_json, str),
        (canonical_identity_json_bytes, bytes),
    ],
)
def test_identity_renderer_runtime_annotations_resolve(
    renderer: Any,
    return_type: type[str] | type[bytes],
) -> None:
    assert get_type_hints(renderer) == {
        "document": IdentityDocument,
        "return": return_type,
    }


def test_canonical_identity_json_is_compact_sorted() -> None:
    doc = build_identity_document(
        schema="example.config",
        schema_version=1,
        payload={"b": 1, "a": 2},
    )
    assert canonical_identity_json(doc) == (
        '{"payload":{"a":2,"b":1},'
        '"schema":"example.config","schema_version":1}'
    )


def test_canonical_identity_bytes_are_exact_text_utf8() -> None:
    doc = build_identity_document(
        schema="example.unicode",
        schema_version=2,
        payload={"text": "héllo 日本語 🎯"},
    )
    assert canonical_identity_json_bytes(doc) == canonical_identity_json(
        doc
    ).encode("utf-8")


def test_identity_document_hash_is_full_lowercase_sha256() -> None:
    doc = build_identity_document(
        schema="s", schema_version=1, payload={"k": "v"}
    )
    hash_value = identity_document_hash(doc)
    assert len(hash_value) == SHA256_HEX_LENGTH
    assert hash_value == hash_value.lower()
    assert all(c in "0123456789abcdef" for c in hash_value)


def test_compute_identity_hash_one_shot_matches_two_step() -> None:
    document = {
        "schema": "s",
        "schema_version": 1,
        "payload": {"k": "v"},
    }
    two_step = identity_document_hash(validate_identity_document(document))
    result = compute_identity_hash(document)
    assert type(result) is Sha256Digest
    assert result == two_step


def test_identity_document_hash_has_no_truncation_parameter() -> None:
    import inspect

    # The identity path exposes no truncation/prefix parameter; the only
    # parameter is the validated document.
    params = list(inspect.signature(identity_document_hash).parameters)
    assert params == ["document"]
    doc = build_identity_document(schema="s", schema_version=1, payload={})
    # Passing a length keyword is a plain TypeError at runtime.
    kwargs: dict[str, Any] = {"document": doc, "length": 16}
    with pytest.raises(TypeError):
        identity_document_hash(**kwargs)


# --------------------------------------------------------------------------
# Equivalence: equivalent documents -> identical JSON text + identical hash
# --------------------------------------------------------------------------


def _permuted_dicts(
    pairs: list[tuple[str, Jsonable]],
) -> list[dict[str, Jsonable]]:
    return [dict(order) for order in itertools.permutations(pairs)]


def test_key_order_does_not_affect_canonical_json_or_hash() -> None:
    pairs: list[tuple[str, Jsonable]] = [
        ("gamma", 3),
        ("alpha", 1),
        ("beta", 2),
    ]
    docs = [
        build_identity_document(schema="s", schema_version=1, payload=payload)
        for payload in _permuted_dicts(pairs)
    ]
    canonical_values = {canonical_identity_json(d) for d in docs}
    hashes = {identity_document_hash(d) for d in docs}
    assert len(canonical_values) == 1
    assert len(hashes) == 1


def test_nested_dict_insertion_order_does_not_affect_hash() -> None:
    doc_a = build_identity_document(
        schema="s",
        schema_version=1,
        payload={"outer": {"x": 1, "y": 2}, "z": [1, 2]},
    )
    doc_b = build_identity_document(
        schema="s",
        schema_version=1,
        payload={"z": [1, 2], "outer": {"y": 2, "x": 1}},
    )
    assert canonical_identity_json(doc_a) == canonical_identity_json(doc_b)
    assert identity_document_hash(doc_a) == identity_document_hash(doc_b)


def test_list_order_is_significant_for_identity() -> None:
    doc_a = build_identity_document(
        schema="s", schema_version=1, payload={"items": [1, 2, 3]}
    )
    doc_b = build_identity_document(
        schema="s", schema_version=1, payload={"items": [3, 2, 1]}
    )
    assert identity_document_hash(doc_a) != identity_document_hash(doc_b)


def test_schema_version_bump_changes_identity() -> None:
    payload = {"identity_field": "value"}
    v1 = build_identity_document(schema="s", schema_version=1, payload=payload)
    v2 = build_identity_document(schema="s", schema_version=2, payload=payload)
    assert identity_document_hash(v1) != identity_document_hash(v2)


# --------------------------------------------------------------------------
# Display-only prefix helper
# --------------------------------------------------------------------------


@pytest.mark.parametrize("length", [1, 32, SHA256_HEX_LENGTH])
def test_identity_hash_prefix_is_leading_slice(length: int) -> None:
    doc = build_identity_document(schema="s", schema_version=1, payload={})
    full = identity_document_hash(doc)
    result = identity_hash_prefix(full, length)
    assert type(result) is str
    assert len(result) == length
    assert full.startswith(result)


@pytest.mark.parametrize("length", [0, -1, 65])
def test_identity_hash_prefix_rejects_bad_length(length: int) -> None:
    doc = build_identity_document(schema="s", schema_version=1, payload={})
    full = identity_document_hash(doc)
    with pytest.raises(ValueError, match="prefix length"):
        identity_hash_prefix(full, length)


def test_identity_hash_prefix_rejects_non_identity_hash() -> None:
    with pytest.raises(ValueError, match="identity hash"):
        identity_hash_prefix("tooshort", 4)


def test_identity_hash_prefix_rejects_uppercase_digest() -> None:
    with pytest.raises(ValueError, match="identity hash"):
        identity_hash_prefix("A" * SHA256_HEX_LENGTH, 4)


# --------------------------------------------------------------------------
# Golden vectors: committed for cross-repository reuse
# --------------------------------------------------------------------------


def _golden_cases() -> dict[str, dict[str, Any]]:
    return json.loads(GOLDEN_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("name", sorted(_golden_cases()))
def test_golden_identity_case_reproduces(name: str) -> None:
    case = _golden_cases()[name]
    document = case["document"]
    doc = validate_identity_document(document)
    assert canonical_identity_json(doc) == case["canonical_json"]
    assert (
        canonical_identity_json_bytes(doc) == case["canonical_json"].encode()
    )
    assert identity_document_hash(doc) == case["identity_hash"]
    assert compute_identity_hash(document) == case["identity_hash"]


def test_golden_hashes_are_full_length_and_unique() -> None:
    cases = _golden_cases()
    hashes = [c["identity_hash"] for c in cases.values()]
    assert all(len(h) == SHA256_HEX_LENGTH for h in hashes)
    assert len(set(hashes)) == len(hashes)
