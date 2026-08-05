"""Contract tests for the shared nominal full SHA-256 digest boundary."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from dr_serialize import (
    Sha256Digest,
    Sha256DigestError,
    build_identity_document,
    identity_document_hash,
    json_hash,
)

VALID_DIGEST = "0123456789abcdef" * 4


class DigestModel(BaseModel):
    model_config = ConfigDict(strict=True)

    digest: Sha256Digest


def test_parse_accepts_exact_lowercase_hex_boundary() -> None:
    digest = Sha256Digest.parse(VALID_DIGEST)
    assert digest == VALID_DIGEST
    assert isinstance(digest, Sha256Digest)


@pytest.mark.parametrize(
    "value",
    [
        "a" * 63,
        "a" * 65,
        "a" * 16,
        "A" * 64,
        ("a" * 63) + "g",
        ("a" * 63) + "-",
        ("a" * 63) + "é",
        ("a" * 63) + " ",
        "sha256:" + ("a" * 64),
    ],
)
def test_parse_rejects_every_non_digest_class(value: str) -> None:
    with pytest.raises(Sha256DigestError):
        Sha256Digest.parse(value)


@pytest.mark.parametrize("value", [None, b"a" * 64, 1])
def test_parse_rejects_non_strings(value: Any) -> None:
    with pytest.raises(Sha256DigestError):
        Sha256Digest.parse(value)


def test_full_hash_functions_return_nominal_digest() -> None:
    document = build_identity_document(
        schema="example", schema_version=1, payload={"x": 1}
    )
    assert isinstance(json_hash({"x": 1}), Sha256Digest)
    assert isinstance(identity_document_hash(document), Sha256Digest)


def test_truncated_json_hash_is_only_a_display_string() -> None:
    prefix = json_hash({"x": 1}, length=16)
    assert type(prefix) is str
    with pytest.raises(Sha256DigestError):
        Sha256Digest.parse(prefix)


def test_pydantic_type_adapter_validates_and_serializes() -> None:
    adapter = TypeAdapter(Sha256Digest)
    digest = adapter.validate_python(VALID_DIGEST)
    assert isinstance(digest, Sha256Digest)
    assert adapter.dump_python(digest, mode="json") == VALID_DIGEST
    assert adapter.dump_json(digest) == f'"{VALID_DIGEST}"'.encode()


@pytest.mark.parametrize(
    "value",
    ["A" * 64, "a" * 63, "a" * 65, b"a" * 64, 1],
)
def test_pydantic_type_adapter_rejects_malformed_or_coerced_input(
    value: Any,
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Sha256Digest).validate_python(value)


def test_strict_pydantic_model_round_trip() -> None:
    model = DigestModel.model_validate({"digest": VALID_DIGEST})
    assert isinstance(model.digest, Sha256Digest)
    assert model.model_dump(mode="json") == {"digest": VALID_DIGEST}
    assert DigestModel.model_validate_json(model.model_dump_json()) == model


def test_pydantic_json_schema_pins_digest_shape() -> None:
    schema = TypeAdapter(Sha256Digest).json_schema()
    assert schema == {
        "maxLength": 64,
        "minLength": 64,
        "pattern": "^[0-9a-f]{64}$",
        "type": "string",
    }
