from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from dr_serialize._core.diagnostics import detail_repr
from dr_serialize._core.json_values import Jsonable
from dr_serialize._core.strict_json import _validate_strict_json
from dr_serialize.canonical.profile import (
    _canonical_failure_detail,
    _find_canonical_json_failure,
)
from dr_serialize.identity.errors import IdentityDocumentError

IDENTITY_DOCUMENT_FIELDS = ("schema", "schema_version", "payload")


@dataclass(frozen=True, slots=True, init=False)
class IdentityDocument:
    """An exact three-field identity document using deep-copy boundaries.

    Construction validates the complete document against strict JSON and
    Canonical JSON Text profile v1. Construction and payload access apply
    ``copy.deepcopy``; accepted custom container subclasses control whether
    that protocol yields isolation.
    """

    schema: str
    schema_version: int
    _payload: Jsonable = field(repr=False)

    def __init__(
        self,
        schema: str,
        schema_version: int,
        payload: Jsonable,
    ) -> None:
        """Validate the public constructor around payload deep-copying.

        Strict validation prevents ``json.dumps`` from silently coercing
        non-string keys into colliding identity documents.
        """
        if not isinstance(schema, str):
            raise IdentityDocumentError(
                path=("schema",),
                reason="field must be a string",
                detail=detail_repr(schema),
            )
        if isinstance(schema_version, bool) or not isinstance(
            schema_version, int
        ):
            raise IdentityDocumentError(
                path=("schema_version",),
                reason="field must be an integer",
                detail=detail_repr(schema_version),
            )
        _validate_strict_json(payload, ("payload",))
        _validate_canonical_profile(schema, schema_version, payload)
        stored_payload = copy.deepcopy(payload)
        _validate_strict_json(stored_payload, ("payload",))
        _validate_canonical_profile(schema, schema_version, stored_payload)
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "_payload", stored_payload)

    @property
    def payload(self) -> Jsonable:
        """Return ``copy.deepcopy`` applied to the stored identity payload."""
        return copy.deepcopy(self._payload)

    def to_json_dict(self) -> dict[str, Jsonable]:
        """Return the exact document using the payload copy protocol."""
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }


def validate_identity_document(
    document: dict[Any, Any],
) -> IdentityDocument:
    """Validate an exact ``schema``, ``schema_version``, ``payload`` mapping.

    Envelope and profile failures raise ``IdentityDocumentError``; payload
    values outside strict JSON raise ``StrictJsonError``.
    """
    if not isinstance(document, dict):
        raise IdentityDocumentError(
            path=(),
            reason="document must be an object",
            detail=detail_repr(document),
        )
    keys = set(document)
    expected = set(IDENTITY_DOCUMENT_FIELDS)
    missing = expected - keys
    if missing:
        raise IdentityDocumentError(
            path=(),
            reason=f"missing field(s): {sorted(missing)}",
            detail=detail_repr(sorted(keys, key=repr)),
        )
    extra = keys - expected
    if extra:
        raise IdentityDocumentError(
            path=(),
            reason=f"unexpected field(s): {sorted(extra, key=repr)}",
            detail=detail_repr(sorted(keys, key=repr)),
        )
    return IdentityDocument(
        schema=document["schema"],
        schema_version=document["schema_version"],
        payload=document["payload"],
    )


def build_identity_document(
    *,
    schema: str,
    schema_version: int,
    payload: Any,
) -> IdentityDocument:
    return validate_identity_document(
        {
            "schema": schema,
            "schema_version": schema_version,
            "payload": payload,
        }
    )


def _validate_canonical_profile(
    schema: str,
    schema_version: int,
    payload: Jsonable,
) -> None:
    prospective_document: dict[str, Jsonable] = {
        "schema": schema,
        "schema_version": schema_version,
        "payload": payload,
    }
    failure = _find_canonical_json_failure(prospective_document)
    if failure is None:
        return
    reason = _canonical_failure_detail(failure) or failure.reason
    raise IdentityDocumentError(
        path=failure.path,
        reason=reason,
        detail=reason,
    )
