"""Contract tests for canonical JSON and digests.

The golden fixture in ``tests/fixtures/hashing_golden.json`` was captured
from whetstone-ai before extraction; byte-identical reproduction is the
migration acceptance gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dr_serialize import (
    canonical_json,
    sha256_json_digest,
)
from dr_serialize.hashing import SHA256_HEX_DIGEST_LENGTH

GOLDEN_FIXTURE = Path(__file__).parent / "fixtures" / "hashing_golden.json"
GOLDEN_TRUNCATED_LENGTH = 16


def test_canonical_json_sorts_keys_and_compacts() -> None:
    value = {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}}
    assert canonical_json(value) == (
        '{"a":[1,2],"b":1,"c":{"y":true,"z":null}}'
    )


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        canonical_json(float("nan"))


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
