"""Contract tests for the identity path.

Covers strict JSON validation and its rejection classes, the exact
three-field Identity Document, Canonical Identity JSON, and the full
Identity Hash. The golden fixture in ``tests/fixtures/identity_golden.json``
is committed for reuse by other repos; byte-identical canonical JSON and
identical hashes are the cross-repository acceptance gate.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, cast

import pytest

from dr_serialize import (
    StrictJsonError,
    IdentityDocument,
    IdentityDocumentError,
    Jsonable,
    build_identity_document,
    canonical_identity_json,
    compute_identity_hash,
    identity_document_hash,
    identity_hash_prefix,
    validate_strict_json,
    validate_identity_document,
)
from dr_serialize.canonical import SHA256_HEX_LENGTH

GOLDEN_FIXTURE = (
    Path(__file__).parent / "fixtures" / "identity_golden.json"
)


# --------------------------------------------------------------------------
# Strict JSON validation: acceptance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -1,
        42,
        9007199254740992,
        0.0,
        -0.001,
        1e300,
        "",
        "text",
        [],
        {},
        [1, "two", None, True, [3, 4]],
        {"a": 1, "b": {"c": [None, False]}},
        {"nested": {"deep": {"deeper": [1, {"x": "y"}]}}},
    ],
)
def test_validate_strict_json_accepts_strict_json(value: Any) -> None:
    assert validate_strict_json(value) is value


def test_validate_strict_json_accepts_numeric_string_keys() -> None:
    value = {"10": "ten", "2": "two", "1": "one"}
    assert validate_strict_json(value) is value


# --------------------------------------------------------------------------
# Strict JSON validation: rejection, one test per invalid class
# --------------------------------------------------------------------------


def test_rejects_non_json_value_at_root() -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(object())
    exc = exc_info.value
    assert exc.path == ()
    assert exc.reason == "unsupported type"
    assert exc.type_name == "object"


def test_rejects_non_json_value_with_jsonpath_location() -> None:
    value = {"k": [1, object()]}
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.path == ("k", 1)
    assert exc.reason == "unsupported type"
    assert set(exc.diagnostics()) == {
        "path",
        "detail",
        "reason",
        "type_name",
    }
    assert exc.diagnostics()["path"] == ["k", 1]


@pytest.mark.parametrize(
    "bad_value", [float("nan"), float("inf"), float("-inf")]
)
def test_rejects_non_finite_number(bad_value: float) -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json({"x": [0.0, bad_value]})
    exc = exc_info.value
    assert exc.path == ("x", 1)
    assert exc.reason == "non-finite number"
    assert exc.type_name == "float"


@pytest.mark.parametrize("bad_key", [1, 2.0, None, True, (1, 2)])
def test_rejects_non_string_object_key(bad_key: Any) -> None:
    value = {"ok": {bad_key: "v"}}
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.path == ("ok",)
    assert exc.reason == "non-string object key"


def test_rejects_dict_reference_cycle() -> None:
    value: dict[str, Any] = {"a": 1}
    value["self"] = value
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.reason == "reference cycle"
    assert exc.type_name == "dict"


def test_rejects_list_reference_cycle() -> None:
    inner: list[Any] = [1]
    value = {"items": inner}
    inner.append(inner)
    with pytest.raises(StrictJsonError) as exc_info:
        validate_strict_json(value)
    exc = exc_info.value
    assert exc.reason == "reference cycle"
    assert exc.type_name == "list"


def test_repeated_shared_subtree_is_not_a_cycle() -> None:
    shared = {"k": "v"}
    value = {"a": shared, "b": shared}
    assert validate_strict_json(value) is value


@pytest.mark.parametrize(
    "bad_value",
    [
        b"bytes",
        (1, 2),
        {1, 2},
        object(),
        complex(1, 2),
    ],
)
def test_rejects_assorted_non_json_types(bad_value: Any) -> None:
    with pytest.raises(StrictJsonError):
        validate_strict_json(bad_value)


# --------------------------------------------------------------------------
# Identity Document: exact three-field shape
# --------------------------------------------------------------------------


def test_validate_identity_document_accepts_exact_shape() -> None:
    doc = validate_identity_document(
        {
            "schema": "example.config",
            "schema_version": 1,
            "payload": {"identity_field": "value"},
        }
    )
    assert isinstance(doc, IdentityDocument)
    assert doc.schema == "example.config"
    assert doc.schema_version == 1
    assert doc.payload == {"identity_field": "value"}
    assert doc.to_json_dict() == {
        "schema": "example.config",
        "schema_version": 1,
        "payload": {"identity_field": "value"},
    }


def test_build_identity_document_matches_validate() -> None:
    built = build_identity_document(
        schema="s", schema_version=2, payload={"a": 1}
    )
    validated = validate_identity_document(
        {"schema": "s", "schema_version": 2, "payload": {"a": 1}}
    )
    assert built == validated


def test_document_rejects_missing_field() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            {"schema": "s", "schema_version": 1},
        )
    assert "missing" in exc_info.value.reason


def test_document_rejects_extra_field() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            {
                "schema": "s",
                "schema_version": 1,
                "payload": {},
                "extra": "nope",
            }
        )
    assert "unexpected" in exc_info.value.reason
    assert exc_info.value.diagnostics()["reason"] == exc_info.value.reason


def test_document_rejects_non_mapping() -> None:
    with pytest.raises(IdentityDocumentError):
        validate_identity_document(cast("Any", ["not", "a", "dict"]))


def test_document_rejects_non_string_schema() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            {"schema": 1, "schema_version": 1, "payload": {}},
        )
    assert exc_info.value.path == ("schema",)


@pytest.mark.parametrize("bad_version", ["1", 1.0, True, None])
def test_document_rejects_non_int_schema_version(bad_version: Any) -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            {
                "schema": "s",
                "schema_version": bad_version,
                "payload": {},
            }
        )
    assert exc_info.value.path == ("schema_version",)


def test_document_payload_strict_json_error_has_payload_path() -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        validate_identity_document(
            {
                "schema": "s",
                "schema_version": 1,
                "payload": {"bad": object()},
            }
        )
    assert exc_info.value.path == ("payload", "bad")


def test_document_rejects_non_finite_in_payload() -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        build_identity_document(
            schema="s",
            schema_version=1,
            payload={"x": float("inf")},
        )
    assert exc_info.value.path == ("payload", "x")


# --------------------------------------------------------------------------
# Direct IdentityDocument(...) construction is validated too
# --------------------------------------------------------------------------


def test_direct_construction_rejects_non_string_key_payload() -> None:
    """The exported constructor validates the payload like the builders.

    A directly constructed document with non-string dict keys must raise a
    typed :class:`StrictJsonError` at construction, not silently coerce the
    keys via ``json.dumps`` when hashed or canonicalized.
    """
    with pytest.raises(StrictJsonError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=cast("Any", {1: "a", 2: "b"}),
        )
    assert exc_info.value.path == ("payload",)
    assert exc_info.value.reason == "non-string object key"


def test_direct_construction_rejects_non_json_payload() -> None:
    with pytest.raises(StrictJsonError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=cast("Any", {"bad": object()}),
        )
    assert exc_info.value.path == ("payload", "bad")


def test_direct_construction_rejects_bad_schema_types() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        IdentityDocument(
            schema=cast("Any", 1), schema_version=1, payload={}
        )
    assert exc_info.value.path == ("schema",)
    bool_version: Any = True
    with pytest.raises(IdentityDocumentError) as version_info:
        IdentityDocument(
            schema="s", schema_version=bool_version, payload={}
        )
    assert version_info.value.path == ("schema_version",)


def test_int_key_payload_cannot_collide_with_string_key_document() -> None:
    """The int/enum-key coercion collision is impossible by construction.

    Previously an int-keyed ``{1: 'x', 2: 'y'}`` payload hashed identically
    to the string-keyed ``{'1': 'x', '2': 'y'}`` document, because
    ``json.dumps`` coerced the keys. The int-keyed document must now fail to
    construct at all, so no collision can occur.
    """
    string_keyed = IdentityDocument(
        schema="s",
        schema_version=1,
        payload={"1": "x", "2": "y"},
    )
    # The string-keyed document hashes fine.
    assert len(identity_document_hash(string_keyed)) == SHA256_HEX_LENGTH
    # The int-keyed document cannot be constructed, so it cannot collide.
    with pytest.raises(StrictJsonError):
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=cast("Any", {1: "x", 2: "y"}),
        )


# --------------------------------------------------------------------------
# Canonical Identity JSON and Identity Hash
# --------------------------------------------------------------------------


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
    assert compute_identity_hash(document) == two_step


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
# Equivalence: equivalent documents -> byte-identical JSON + identical hash
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
        build_identity_document(
            schema="s", schema_version=1, payload=payload
        )
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
    v1 = build_identity_document(
        schema="s", schema_version=1, payload=payload
    )
    v2 = build_identity_document(
        schema="s", schema_version=2, payload=payload
    )
    assert identity_document_hash(v1) != identity_document_hash(v2)


# --------------------------------------------------------------------------
# Display-only prefix helper
# --------------------------------------------------------------------------


def test_identity_hash_prefix_is_leading_slice() -> None:
    doc = build_identity_document(schema="s", schema_version=1, payload={})
    full = identity_document_hash(doc)
    prefix = identity_hash_prefix(full, 12)
    assert len(prefix) == 12
    assert full.startswith(prefix)


@pytest.mark.parametrize("length", [0, -1, 65])
def test_identity_hash_prefix_rejects_bad_length(length: int) -> None:
    doc = build_identity_document(schema="s", schema_version=1, payload={})
    full = identity_document_hash(doc)
    with pytest.raises(ValueError, match="prefix length"):
        identity_hash_prefix(full, length)


def test_identity_hash_prefix_rejects_non_identity_hash() -> None:
    with pytest.raises(ValueError, match="identity hash"):
        identity_hash_prefix("tooshort", 4)


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
    assert identity_document_hash(doc) == case["identity_hash"]
    assert compute_identity_hash(document) == case["identity_hash"]


def test_golden_hashes_are_full_length_and_unique() -> None:
    cases = _golden_cases()
    hashes = [c["identity_hash"] for c in cases.values()]
    assert all(len(h) == SHA256_HEX_LENGTH for h in hashes)
    assert len(set(hashes)) == len(hashes)


# --------------------------------------------------------------------------
# Separation from the diagnostic normalization lane
# --------------------------------------------------------------------------


def test_identity_path_does_not_coerce_via_diagnostic_normalization() -> None:
    """A value the Serializer would normalize is rejected, not coerced.

    The diagnostic lane (Serializer.to_jsonable) turns arbitrary objects
    into JSON-safe data; the identity path must never do that. A plain
    object with a ``__dict__`` would be normalized diagnostically but must
    be rejected here so it cannot silently collapse onto an identity.
    """
    import pydantic

    from dr_serialize import Serializer, postgres_jsonb_limits

    class Model(pydantic.BaseModel):
        name: str
        count: int

    model = Model(name="n", count=1)

    # Diagnostic lane accepts and normalizes it.
    normalized = Serializer(limits=postgres_jsonb_limits()).to_jsonable(model)
    assert normalized == {"name": "n", "count": 1}

    # Identity path rejects the un-normalized model outright.
    with pytest.raises(StrictJsonError):
        validate_strict_json(model)
    with pytest.raises(StrictJsonError):
        build_identity_document(
            schema="s", schema_version=1, payload={"model": model}
        )
