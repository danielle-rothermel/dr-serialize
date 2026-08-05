"""The exact validated Identity Document shape and snapshot semantics."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from dr_serialize._core.diagnostics import detail_repr
from dr_serialize._core.json_values import Jsonable
from dr_serialize._core.strict_json import _validate_strict_json
from dr_serialize.identity.errors import IdentityDocumentError

IDENTITY_DOCUMENT_FIELDS = ("schema", "schema_version", "payload")


@dataclass(frozen=True, slots=True, init=False)
class IdentityDocument:
    """A validated, self-describing, versioned Identity Document.

    Construction itself validates, so every
    ``IdentityDocument`` -- whether built via :func:`build_identity_document`,
    :func:`validate_identity_document`, or the exported constructor directly
    -- always holds a payload validated as a strict JSON value with the
    exact three-field shape. The owning domain chooses ``schema``,
    ``schema_version``, and the complete ``payload``; dr-serialize validates
    them.

    **Snapshot semantics.** The constructor takes a deep copy of ``payload``
    after validation and stores it privately, so the document owns an
    independent snapshot: later mutation of the caller's original object
    cannot affect the document or its Identity Hash. The public
    :attr:`payload` and :meth:`to_json_dict` each return a fresh deep copy,
    so mutating any returned alias never touches the stored payload.
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
        """Reject any document the validators would reject.

        The public constructor is exported, so it must enforce the same
        invariant as :func:`build_identity_document` /
        :func:`validate_identity_document`: ``schema`` is a string,
        ``schema_version`` is a real int (not bool), and ``payload`` is
        a strict JSON value. Without this, a directly constructed document
        with, for example, int/enum dict keys would be handed straight to
        ``json.dumps`` and have its keys silently coerced to strings,
        producing a valid-looking Identity Hash that collides with the
        string-keyed document. Validating here raises the typed
        :class:`IdentityDocumentError` / :class:`StrictJsonError` instead.
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
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "_payload", copy.deepcopy(payload))

    @property
    def payload(self) -> Jsonable:
        """Return a fresh deep copy of the owned identity payload."""
        return copy.deepcopy(self._payload)

    def to_json_dict(self) -> dict[str, Jsonable]:
        """Return the exact three-field document as a plain dict.

        The ``payload`` is deep-copied, so mutating the returned mapping (or
        any nested container) never affects this document or its hash.
        """
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }


def validate_identity_document(
    document: dict[Any, Any],
) -> IdentityDocument:
    """Validate a dict as an exact-shape Identity Document.

    Requires exactly the fields ``schema`` (str), ``schema_version`` (int,
    not bool), and ``payload`` (a strict JSON value). Missing fields, extra
    fields, and wrong field types raise :class:`IdentityDocumentError`;
    values inside the payload that are not strict JSON values raise
    :class:`StrictJsonError` with a ``("payload", ...)`` path.
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
    """Validate and construct an :class:`IdentityDocument` from parts.

    A thin convenience over :func:`validate_identity_document` for callers
    that already hold the three fields separately. The owning domain still
    chooses every value; dr-serialize only validates.
    """
    return validate_identity_document(
        {
            "schema": schema,
            "schema_version": schema_version,
            "payload": payload,
        }
    )
