"""Typed failures for identity document validation."""

from __future__ import annotations

from typing import Any

from dr_serialize._core.diagnostics import JsonPath, SerializationError


class IdentityDocumentError(SerializationError):
    """An Identity Document does not have the exact three-field shape.

    Raised by :func:`validate_identity_document` when the document is not a
    mapping, is missing a required field, carries an extra field, or has a
    field of the wrong type. Values inside the payload that are not strict
    JSON values raise :class:`StrictJsonError` instead.
    """

    def __init__(
        self,
        *,
        path: JsonPath,
        reason: str,
        detail: str,
    ) -> None:
        self.path = path
        self.reason = reason
        self.detail = detail
        super().__init__(
            f"invalid identity document at path {path!r}: {reason}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "reason": self.reason,
        }
