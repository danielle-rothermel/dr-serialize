"""Contract tests for Canonical JSON Text and hashes.

The golden fixture in ``tests/fixtures/hashing_golden.json`` was captured
from whetstone-ai before extraction; byte-identical reproduction is the
migration acceptance gate.

The fixture's metadata keys were renamed ``digest`` -> ``hash`` after
capture; the ``value``/``canonical_json`` inputs and all hash values remain
byte-identical to the whetstone-ai capture.
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
    canonical_json_bytes,
    json_hash,
)
from dr_serialize.canonical import SHA256_HEX_LENGTH
from dr_serialize.jsonable import find_json_failure

GOLDEN_FIXTURE = Path(__file__).parent / "fixtures" / "hashing_golden.json"
GOLDEN_TRUNCATED_LENGTH = 16


def test_canonical_json_sorts_keys_and_compacts() -> None:
    value: Jsonable = {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}}
    assert canonical_json(value) == (
        '{"a":[1,2],"b":1,"c":{"y":true,"z":null}}'
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        None,
        {"nested": [1, {"x": True}]},
        "héllo 日本語 🎯",
        'line one\nline two\t"quoted" \\backslash',
        9007199254740992,
        1e300,
    ],
)
def test_canonical_bytes_are_exact_text_utf8(value: Jsonable) -> None:
    assert canonical_json_bytes(value) == canonical_json(value).encode("utf-8")


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(JsonEncodeError) as exc_info:
        canonical_json(float("nan"))

    exc = exc_info.value
    assert exc.path == ()
    assert exc.type_name == "float"
    assert isinstance(exc.underlying, ValueError)


def test_json_hash_full_length() -> None:
    hash_value = json_hash({"k": "v"})
    assert len(hash_value) == SHA256_HEX_LENGTH
    assert hash_value == json_hash({"k": "v"})


@pytest.mark.parametrize("length", [1, 16, 24, 32, 64])
def test_json_hash_truncation(length: int) -> None:
    hash_value = json_hash({"k": "v"}, length=length)
    assert len(hash_value) == length
    assert json_hash({"k": "v"}).startswith(hash_value)


@pytest.mark.parametrize("length", [0, -1, 65])
def test_json_hash_rejects_bad_length(length: int) -> None:
    with pytest.raises(ValueError, match="hash length"):
        json_hash({"k": "v"}, length=length)


class TestCanonicalTypedErrors:
    def test_non_jsonable_value_is_rejected_before_encoding(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def unexpected_dump(_value: object, **_kwargs: object) -> str:
            pytest.fail("json.dumps must not receive a non-Jsonable value")

        monkeypatch.setattr(
            "dr_serialize.canonical.json.dumps",
            unexpected_dump,
        )

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", (1, 2)))

        assert exc_info.value.path == ()
        assert isinstance(exc_info.value.underlying, TypeError)

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

    def test_non_string_key_raises_type_error_underlying(self) -> None:
        value = cast("Jsonable", {"outer": {1: "value"}})
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(value)

        exc = exc_info.value
        assert exc.path == ("outer",)
        assert exc.type_name == "int"
        assert isinstance(exc.underlying, TypeError)

    def test_hash_propagates_json_encode_error(self) -> None:
        value = cast("Jsonable", {"k": object()})
        with pytest.raises(JsonEncodeError):
            json_hash(value)

    def test_canonical_bytes_preserve_rejection(self) -> None:
        value = cast("Jsonable", {"k": object()})
        with pytest.raises(JsonEncodeError):
            canonical_json_bytes(value)

    def test_hash_length_validation_stays_value_error(self) -> None:
        with pytest.raises(ValueError, match="hash length"):
            json_hash({"a": 1}, length=0)


class TestCycleAndKeyDiagnostics:
    def test_cyclic_dict_raises_json_encode_error(self) -> None:
        cyclic: dict[str, Any] = {"a": 1}
        cyclic["self"] = cyclic
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", cyclic))
        assert isinstance(exc_info.value.underlying, TypeError)
        with pytest.raises(JsonEncodeError):
            json_hash(cast("Jsonable", cyclic))

    def test_cyclic_list_raises_json_encode_error(self) -> None:
        cyclic: list[Any] = [1, 2]
        cyclic.append(cyclic)
        with pytest.raises(JsonEncodeError):
            canonical_json(cast("Jsonable", cyclic))
        with pytest.raises(JsonEncodeError):
            json_hash(cast("Jsonable", cyclic))

    def test_find_json_failure_reports_non_string_key_with_path(
        self,
    ) -> None:
        found = find_json_failure({"outer": {1: 2}})
        assert found is not None
        path, leaf = found
        assert path == ("outer",)
        assert leaf == 1

    def test_find_json_failure_reports_top_level_non_string_key(
        self,
    ) -> None:
        found = find_json_failure({1: 2})
        assert found is not None
        path, leaf = found
        assert path == ()
        assert leaf == 1

    def test_find_json_failure_reports_cycle_instead_of_recursing(
        self,
    ) -> None:
        cyclic: dict[str, Any] = {}
        cyclic["self"] = cyclic
        found = find_json_failure(cyclic)
        assert found is not None
        path, _leaf = found
        assert path == ("self",)


def _golden_cases() -> dict[str, dict[str, Any]]:
    return json.loads(GOLDEN_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("name", sorted(_golden_cases()))
def test_golden_hashing_case_reproduces(name: str) -> None:
    case = _golden_cases()[name]
    value = case["value"]
    assert canonical_json(value) == case["canonical_json"]
    assert canonical_json_bytes(value) == case["canonical_json"].encode()
    assert json_hash(value) == case["hash"]
    assert (
        json_hash(value, length=GOLDEN_TRUNCATED_LENGTH)
        == case["truncated_hash"]
    )
