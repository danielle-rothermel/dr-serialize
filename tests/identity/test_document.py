from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from dr_serialize import (
    IdentityDocument,
    IdentityDocumentError,
    Jsonable,
    StrictJsonError,
    build_identity_document,
    canonical_identity_json,
    canonical_identity_json_bytes,
    identity_document_hash,
    validate_identity_document,
    validate_strict_json,
)
from dr_serialize._core.digests import SHA256_HEX_LENGTH


def _nested_list(depth: int, leaf: Jsonable = 0) -> Jsonable:
    value = leaf
    for _ in range(depth):
        value = [value]
    return value


class _MisleadingAbsInt(int):
    def __abs__(self) -> int:
        return 0


class _RaisingAbsInt(int):
    def __abs__(self) -> int:
        raise RuntimeError("absolute value failed")


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


def test_extra_field_with_non_string_key_raises_identity_error() -> None:
    # Mixed key types must produce IdentityDocumentError, not leak TypeError
    # from diagnostic key sorting.
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            cast(
                "Any",
                {
                    "schema": "s",
                    "schema_version": 1,
                    "payload": {},
                    42: "x",
                },
            )
        )
    assert "unexpected" in exc_info.value.reason


def test_missing_field_with_non_string_key_raises_identity_error() -> None:
    # Mixed key types must produce IdentityDocumentError, not leak TypeError
    # from diagnostic key sorting.
    with pytest.raises(IdentityDocumentError) as exc_info:
        validate_identity_document(
            cast("Any", {"schema": "s", "payload": {}, 42: "x"})
        )
    assert "missing" in exc_info.value.reason


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


def test_document_accepts_exact_canonical_depth_limit() -> None:
    document = build_identity_document(
        schema="s",
        schema_version=1,
        payload=_nested_list(199),
    )

    assert len(identity_document_hash(document)) == SHA256_HEX_LENGTH


@pytest.mark.parametrize(
    "construct",
    [
        lambda payload: IdentityDocument("s", 1, payload),
        lambda payload: build_identity_document(
            schema="s", schema_version=1, payload=payload
        ),
        lambda payload: validate_identity_document(
            {"schema": "s", "schema_version": 1, "payload": payload}
        ),
    ],
)
def test_document_rejects_payload_beyond_canonical_depth_limit(
    construct: Callable[[Jsonable], IdentityDocument],
) -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        construct(_nested_list(200))

    assert exc_info.value.path == ("payload", *((0,) * 199))
    assert exc_info.value.reason == "container depth 201 exceeds maximum 200"


def test_document_rejects_payload_integer_beyond_canonical_limit() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        build_identity_document(
            schema="s",
            schema_version=1,
            payload={"n": 10**640},
        )

    assert exc_info.value.path == ("payload", "n")
    assert (
        exc_info.value.reason == "integer exceeds maximum 640 decimal digits"
    )


def test_document_rejects_schema_version_beyond_canonical_limit() -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        IdentityDocument(schema="s", schema_version=10**640, payload={})

    assert exc_info.value.path == ("schema_version",)
    assert (
        exc_info.value.reason == "integer exceeds maximum 640 decimal digits"
    )


@pytest.mark.parametrize(
    "version_type",
    [_MisleadingAbsInt, _RaisingAbsInt],
)
def test_document_integer_bound_cannot_be_bypassed_by_subclass(
    version_type: type[int],
) -> None:
    with pytest.raises(IdentityDocumentError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=version_type(10**640),
            payload={},
        )

    assert exc_info.value.path == ("schema_version",)


def test_broken_path_repr_cannot_replace_identity_document_error() -> None:
    class BadReprStr(str):
        __slots__ = ()

        def __repr__(self) -> str:
            raise RuntimeError("representation failed")

    key = BadReprStr("n")
    with pytest.raises(IdentityDocumentError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload={key: 10**640},
        )

    assert exc_info.value.path == ("payload", key)


def test_document_revalidates_deep_copied_payload() -> None:
    class InvalidDeepCopyList(list[Jsonable]):
        def __deepcopy__(self, _memo: dict[int, Any]) -> Any:
            return object()

    with pytest.raises(StrictJsonError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=InvalidDeepCopyList(),
        )

    assert exc_info.value.path == ("payload",)


def test_document_revalidates_canonical_bounds_after_deepcopy() -> None:
    class ExpandingDeepCopyList(list[Jsonable]):
        def __deepcopy__(self, _memo: dict[int, Any]) -> Any:
            return _nested_list(200)

    with pytest.raises(IdentityDocumentError) as exc_info:
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=ExpandingDeepCopyList(),
        )

    assert exc_info.value.path == ("payload", *((0,) * 199))


def test_mutating_original_payload_does_not_change_document() -> None:
    payload: dict[str, Any] = {"a": 1, "nested": {"b": 2}}
    doc = IdentityDocument(schema="s", schema_version=1, payload=payload)
    canonical_before = canonical_identity_json(doc)
    hash_before = identity_document_hash(doc)

    payload["a"] = 999
    payload["nested"]["b"] = 999
    payload["new"] = "added"

    assert canonical_identity_json(doc) == canonical_before
    assert identity_document_hash(doc) == hash_before


def test_mutating_public_payload_does_not_change_document() -> None:
    doc = IdentityDocument(
        "s",
        1,
        {"nested": {"items": [1, 2]}},
    )
    canonical_before = canonical_identity_json_bytes(doc)
    hash_before = identity_document_hash(doc)

    public_payload = cast("dict[str, Any]", doc.payload)
    public_payload["nested"]["items"].append(3)
    public_payload["injected"] = True

    assert doc.payload == {"nested": {"items": [1, 2]}}
    assert canonical_identity_json_bytes(doc) == canonical_before
    assert identity_document_hash(doc) == hash_before


def test_mutating_to_json_dict_result_does_not_change_document() -> None:
    doc = IdentityDocument(
        schema="s", schema_version=1, payload={"nested": {"b": 2}}
    )
    hash_before = identity_document_hash(doc)

    returned = doc.to_json_dict()
    cast("dict[str, Any]", returned["payload"])["nested"]["b"] = 999
    cast("dict[str, Any]", returned["payload"])["injected"] = True

    assert identity_document_hash(doc) == hash_before


def test_direct_construction_rejects_non_string_key_payload() -> None:
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
        IdentityDocument(schema=cast("Any", 1), schema_version=1, payload={})
    assert exc_info.value.path == ("schema",)
    bool_version: Any = True
    with pytest.raises(IdentityDocumentError) as version_info:
        IdentityDocument(schema="s", schema_version=bool_version, payload={})
    assert version_info.value.path == ("schema_version",)


def test_int_key_payload_cannot_collide_with_string_key_document() -> None:
    string_keyed = IdentityDocument(
        schema="s",
        schema_version=1,
        payload={"1": "x", "2": "y"},
    )
    assert len(identity_document_hash(string_keyed)) == SHA256_HEX_LENGTH
    with pytest.raises(StrictJsonError):
        IdentityDocument(
            schema="s",
            schema_version=1,
            payload=cast("Any", {1: "x", 2: "y"}),
        )


def test_identity_path_does_not_coerce_via_diagnostic_normalization() -> None:
    import pydantic

    from dr_serialize import Serializer, postgres_jsonb_limits

    class Model(pydantic.BaseModel):
        name: str
        count: int

    model = Model(name="n", count=1)

    normalized = Serializer(limits=postgres_jsonb_limits()).to_jsonable(model)
    assert normalized == {"name": "n", "count": 1}

    with pytest.raises(StrictJsonError):
        validate_strict_json(model)
    with pytest.raises(StrictJsonError):
        build_identity_document(
            schema="s", schema_version=1, payload={"model": model}
        )
