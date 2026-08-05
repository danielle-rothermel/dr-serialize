"""Canonical JSON text encoding failures."""

from __future__ import annotations

from typing import Any

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
)


class JsonEncodeError(SerializationError):
    def __init__(
        self,
        *,
        path: JsonPath,
        type_name: str,
        detail: str,
        underlying: TypeError | ValueError,
        value_preview: str,
    ) -> None:
        self.path = path
        self.type_name = type_name
        self.detail = detail
        self.underlying = underlying
        self.value_preview = value_preview
        super().__init__(
            "not JSON-serializable at path "
            f"{detail_repr(path)} type {type_name}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "type_name": self.type_name,
            "value_preview": self.value_preview,
            "underlying": repr(self.underlying),
        }
