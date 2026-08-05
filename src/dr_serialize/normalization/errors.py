"""Typed failures raised by policy-driven normalization."""

from __future__ import annotations

from typing import Any, ClassVar

from dr_serialize._core.diagnostics import (
    JsonPath,
    SerializationError,
    detail_repr,
)


def _format_top_level_sizes(
    sizes: dict[str, int],
    *,
    limit: int = 10,
) -> str:
    items = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return ", ".join(f"{key}={size}" for key, size in items)


class MaxDepthExceededError(SerializationError):
    def __init__(
        self,
        *,
        depth: int,
        max_depth: int,
        path: JsonPath,
        value_preview: str,
        detail: str,
    ) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.path = path
        self.value_preview = value_preview
        self.detail = detail
        super().__init__(
            f"max depth {max_depth} exceeded at depth {depth} path "
            f"{detail_repr(path)}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "depth": self.depth,
            "max_depth": self.max_depth,
            "value_preview": self.value_preview,
        }


class PayloadTooLargeError(SerializationError):
    def __init__(  # noqa: PLR0913 -- frozen public diagnostics shape
        self,
        *,
        size_bytes: int,
        max_bytes: int,
        postgres_max_bytes: int,
        path: JsonPath,
        top_level_sizes: dict[str, int],
        preview_head: str,
        preview_tail: str,
        detail: str,
    ) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        self.postgres_max_bytes = postgres_max_bytes
        self.path = path
        self.top_level_sizes = top_level_sizes
        self.preview_head = preview_head
        self.preview_tail = preview_tail
        self.detail = detail
        sizes_summary = _format_top_level_sizes(top_level_sizes)
        sizes_part = f" top keys: {sizes_summary}" if sizes_summary else ""
        super().__init__(
            f"payload {size_bytes} bytes exceeds limit {max_bytes} "
            f"at path {detail_repr(path)}{sizes_part}"
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "size_bytes": self.size_bytes,
            "max_bytes": self.max_bytes,
            "postgres_max_bytes": self.postgres_max_bytes,
            "top_level_sizes": self.top_level_sizes,
            "preview_head": self.preview_head,
            "preview_tail": self.preview_tail,
        }


class ValueTransformError(SerializationError):
    """Base for failures inside a value-transforming handler."""

    message_prefix: ClassVar[str] = "value transform failed"

    def __init__(
        self,
        *,
        path: JsonPath,
        underlying: BaseException,
        value_preview: str,
        detail: str,
    ) -> None:
        self.path = path
        self.underlying = underlying
        self.value_preview = value_preview
        self.detail = detail
        super().__init__(f"{self.message_prefix} at path {detail_repr(path)}")

    def diagnostics(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "detail": self.detail,
            "value_preview": self.value_preview,
            "underlying": repr(self.underlying),
        }


class ModelDumpError(ValueTransformError):
    message_prefix: ClassVar[str] = "pydantic model_dump failed"


class ObjectVarsSerializationError(ValueTransformError):
    message_prefix: ClassVar[str] = "object __dict__ transform failed"
