from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, get_type_hints

import pytest

from dr_serialize import (
    Jsonable,
    JsonEncodeError,
    Sha256Digest,
    canonical_json,
    canonical_json_bytes,
    json_hash,
)
from dr_serialize._core.digests import SHA256_HEX_LENGTH

if TYPE_CHECKING:
    from collections.abc import Callable

# Cross-repository compatibility vectors pin exact canonical text and hashes.
GOLDEN_FIXTURE = Path(__file__).parents[1] / "fixtures" / "hashing_golden.json"
GOLDEN_TRUNCATED_LENGTH = 16


def test_canonical_json_sorts_keys_and_compacts() -> None:
    value: Jsonable = {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}}
    assert canonical_json(value) == (
        '{"a":[1,2],"b":1,"c":{"y":true,"z":null}}'
    )


def test_canonical_json_preserves_array_order() -> None:
    assert canonical_json([3, 1, 2]) == "[3,1,2]"
    value: Jsonable = {"b": ["z", "a", "m"], "a": [3, 1, 2]}
    assert canonical_json(value) == '{"a":[3,1,2],"b":["z","a","m"]}'


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


@pytest.mark.parametrize(
    ("function", "expected_hints"),
    [
        (canonical_json, {"value": Jsonable, "return": str}),
        (canonical_json_bytes, {"value": Jsonable, "return": bytes}),
        (
            json_hash,
            {
                "value": Jsonable,
                "length": int | None,
                "return": Sha256Digest | str,
            },
        ),
    ],
)
def test_canonical_runtime_annotations_resolve(
    function: Callable[..., object],
    expected_hints: dict[str, object],
) -> None:
    hints = get_type_hints(function)
    for name, expected in expected_hints.items():
        assert hints[name] == expected


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
    def test_broken_repr_cannot_replace_json_encode_error(self) -> None:
        class BadRepr:
            def __repr__(self) -> str:
                raise RuntimeError("representation failed")

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", BadRepr()))

        assert exc_info.value.detail == (
            "<repr failed for BadRepr: RuntimeError>"
        )
        assert exc_info.value.value_preview == (
            "<repr failed for BadRepr: RuntimeError>"
        )

    def test_str_subclass_repr_cannot_replace_json_encode_error(self) -> None:
        class RaisingSlice(str):
            __slots__ = ()

            def __getitem__(self, key: object) -> str:
                raise LookupError("slice failed")

        class BadSliceRepr:
            def __repr__(self) -> str:
                return RaisingSlice("rendered")

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", BadSliceRepr()))

        assert exc_info.value.detail == "rendered"
        assert exc_info.value.value_preview == "rendered"

    def test_broken_path_repr_cannot_replace_json_encode_error(self) -> None:
        class BadReprStr(str):
            __slots__ = ()

            def __repr__(self) -> str:
                raise RuntimeError("representation failed")

        key = BadReprStr("bad")
        value = cast("Jsonable", {key: object()})
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(value)

        assert exc_info.value.path == (key,)

    def test_non_jsonable_tuple_raises_typed_error_at_root(self) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", (1, 2)))

        exc = exc_info.value
        assert exc.path == ()
        assert exc.type_name == "tuple"
        assert isinstance(exc.underlying, TypeError)

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

    @pytest.mark.parametrize(
        ("value", "expected_path"),
        [
            ({1: "value"}, ()),
            ({"outer": {1: "value"}}, ("outer",)),
        ],
    )
    def test_non_string_key_raises_typed_error_at_exact_path(
        self,
        value: object,
        expected_path: tuple[str, ...],
    ) -> None:
        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", value))

        exc = exc_info.value
        assert exc.path == expected_path
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


class TestCycleDiagnostics:
    def test_cyclic_dict_raises_typed_error_at_exact_path(self) -> None:
        cyclic: dict[str, Any] = {"a": 1}
        cyclic["self"] = cyclic

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", cyclic))

        exc = exc_info.value
        assert exc.path == ("self",)
        assert exc.type_name == "dict"
        assert isinstance(exc.underlying, TypeError)

    def test_cyclic_list_raises_typed_error_at_exact_path(self) -> None:
        cyclic: list[Any] = [1, 2]
        cyclic.append(cyclic)

        with pytest.raises(JsonEncodeError) as exc_info:
            canonical_json(cast("Jsonable", cyclic))

        exc = exc_info.value
        assert exc.path == (2,)
        assert exc.type_name == "list"
        assert isinstance(exc.underlying, TypeError)


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
