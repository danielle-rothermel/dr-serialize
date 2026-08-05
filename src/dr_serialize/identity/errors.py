from __future__ import annotations

from typing import Any

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
)


class IdentityDocumentError(SerializationError):
    """An identity-envelope or canonical-profile validation failure.

    Payload values outside strict JSON raise ``StrictJsonError`` instead.
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
            f"invalid identity document at path {detail_repr(path)}: {reason}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "reason": self.reason,
        }
