"""Contract tests for canonical JSON and digests.

The golden fixture in ``tests/fixtures/hashing_golden.json`` was captured
from whetstone-ai before extraction; byte-identical reproduction is the
migration acceptance gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from dr_serialize import (
    Jsonable,
    JsonEncodeError,
    canonical_json,
    sha256_json_digest,
)
from dr_serialize.canonical import SHA256_HEX_DIGEST_LENGTH

GOLDEN_FIXTURE = Path(__file__).parent / "fixtures" / "hashing_golden.json"
GOLDEN_TRUNCATED_LENGTH = 16


def test_canonical_json_sorts_keys_and_compacts() -> None:
    value: Jsonable = {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}}
    assert canonical_json(value) == (
        '{"a":[1,2],"b":1,"c":{"y":true,"z":null}}'
    )


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(float("nan"))

    exc = exc_info.value
    assert exc.path == ()
    assert exc.type_name == "float"
    assert isinstance(exc.underlying, ValueError)


def test_sha256_json_digest_full_length() -> None:
    digest = sha256_json_digest({"k": "v"})
    assert len(digest) == SHA256_HEX_DIGEST_LENGTH
    assert digest == sha256_json_digest({"k": "v"})


@pytest.mark.parametrize("length", [1, 16, 24, 32, 64])
def test_sha256_json_digest_truncation(length: int) -> None:
    digest = sha256_json_digest({"k": "v"}, length=length)
    assert len(digest) == length
    assert sha256_json_digest({"k": "v"}).startswith(digest)


@pytest.mark.parametrize("length", [0, -1, 65])
def test_sha256_json_digest_rejects_bad_length(length: int) -> None:
    with pytest.raises(ValueError, match="digest length"):
        sha256_json_digest({"k": "v"}, length=length)


class TestCanonicalTypedErrors:
    def test_non_jsonable_leaf_raises_json_encode_error_with_path(
        self,
    ) -> None:
        value = cast("Jsonable", {"k": [1, object()]})
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(value)

        exc = exc_info.value
        assert exc.path == ("k", 1)
        assert exc.type_name == "object"
        assert isinstance(exc.underlying, TypeError)
        assert set(exc.diagnostics()) == {
            "path",
            "detail",
            "type_name",
            "value_preview",
            "underlying",
        }

    def test_non_finite_float_raises_json_encode_error(self) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json({"x": float("nan")})

        exc = exc_info.value
        assert exc.path == ("x",)
        assert exc.type_name == "float"
        assert isinstance(exc.underlying, ValueError)

    def test_digest_propagates_json_encode_error(self) -> None:
        value = cast("Jsonable", {"k": object()})
        with pytest.raises(JsonEncodeError):
            sha256_json_digest(value)

    def test_digest_length_validation_stays_value_error(self) -> None:
        with pytest.raises(ValueError, match="digest length"):
            sha256_json_digest({"a": 1}, length=0)


def _golden_cases() -> dict[str, dict[str, Any]]:
    return json.loads(GOLDEN_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("name", sorted(_golden_cases()))
def test_golden_hashing_case_reproduces(name: str) -> None:
    case = _golden_cases()[name]
    value = case["value"]
    assert canonical_json(value) == case["canonical_json"]
    assert sha256_json_digest(value) == case["digest"]
    assert (
        sha256_json_digest(value, length=GOLDEN_TRUNCATED_LENGTH)
        == case["truncated_digest"]
    )
