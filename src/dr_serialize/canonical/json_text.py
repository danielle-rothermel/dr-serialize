from __future__ import annotations

import json

from dr_serialize._core.diagnostics import detail_repr, preview_repr
from dr_serialize._core.encoding import TEXT_ENCODING
from dr_serialize._core.json_values import (
    Jsonable,  # noqa: TC001 -- runtime hints
)
from dr_serialize.canonical.errors import JsonEncodeError
from dr_serialize.canonical.profile import (
    _canonical_failure_detail,
    _find_canonical_json_failure,
)


def canonical_json(value: Jsonable) -> str:
    """Render a strict JSON value with Canonical JSON Text profile v1.

    Validates the frozen depth and integer bounds before encoding with the
    profile's fixed ``json.dumps`` flags.
    """
    failure = _find_canonical_json_failure(value)
    if failure is not None:
        profile_detail = _canonical_failure_detail(failure)
        underlying: TypeError | ValueError
        if failure.reason in {
            "maximum container depth",
            "maximum integer digits",
            "non-finite number",
        }:
            underlying = ValueError(profile_detail or failure.reason)
        else:
            underlying = TypeError(failure.reason)
        error = JsonEncodeError(
            path=failure.path,
            type_name=type(failure.leaf).__name__,
            detail=profile_detail or detail_repr(failure.leaf),
            underlying=underlying,
            value_preview=preview_repr(value),
        )
        raise error from underlying

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise JsonEncodeError(
            path=(),
            type_name=type(value).__name__,
            detail=detail_repr(value),
            underlying=error,
            value_preview=preview_repr(value),
        ) from error


def canonical_json_bytes(value: Jsonable, /) -> bytes:
    return canonical_json(value).encode(TEXT_ENCODING)
