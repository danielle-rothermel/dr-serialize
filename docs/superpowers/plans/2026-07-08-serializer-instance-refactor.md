# Instance-Based Serializer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace dr-serialize's global handler registry and ContextVar depth state with an instance-based `Serializer`/`ConversionContext` API, then migrate dr-platform and whetstone-ai in the same sweep.

**Architecture:** A frozen slots dataclass `Serializer` bundles `SerializationLimits` with a tuple of consumer handlers; handlers receive a per-node `ConversionContext` and recurse via `ctx.convert(child, key)`, so the library owns depth/path bookkeeping. The module-global `_registered_handlers` list, the `_ACTIVE_MAX_DEPTH` ContextVar, `convert_value`, and `to_metadata_dict` are deleted. Consumers construct serializers explicitly.

**Tech Stack:** Python 3.12+ (PEP 695 `type` aliases), Pydantic v2, uv, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-07-08-serializer-instance-refactor-design.md`. The limits chunk (frozen `SerializationLimits`, `POSTGRES_JSONB_LIMITS` removal) already landed as `4bccd7e` on branch `serializer-instance-refactor`.

## Global Constraints

- Work on branch `serializer-instance-refactor` in `/Users/daniellerothermel/drotherm/repos/dr-serialize` for Tasks 1–2; Tasks 3–4 run in the sibling consumer repos (paths given per task) on fresh branches.
- Run Python via `uv run ...` in whichever repo you are in. Verification per task: `uv run pytest` and `uv run ruff check .` must both pass.
- Clean break: no shims, aliases, or deprecation layers. Error taxonomy `diagnostics()` shapes are frozen contracts — do not change any diagnostics keys or message formats.
- Final public export list of `dr_serialize` is exactly the 20 names in Task 1 Step 5. Do not add or drop names beyond it.
- Keep diffs surgical: no reformatting or cleanup outside the lines these tasks specify.
- Consumers pin dr-serialize as a git dependency by `rev`. Tasks 3–4 MUST NOT start until Task 2 has produced a merged main SHA.
- If exploring code in the dr-serialize repo, `graphify query "<question>"` first (repo convention); after code changes in dr-serialize, run `graphify update .`.

---

### Task 1: Rewrite the conversion engine around Serializer + ConversionContext

**Files:**
- Create: `src/dr_serialize/_encoding.py`
- Modify: `src/dr_serialize/serialization.py` (full rewrite)
- Modify: `src/dr_serialize/hashing.py:8` (import `TEXT_ENCODING` instead of defining it)
- Modify: `src/dr_serialize/__init__.py` (full rewrite of imports + `__all__`)
- Modify: `tests/support.py`
- Modify: `tests/test_handler_registration.py` (full rewrite)
- Modify: `tests/test_serialization.py` (mechanical port + delete `to_metadata_dict` tests)

**Interfaces:**
- Consumes: `SerializationLimits` / `postgres_jsonb_limits` from the already-landed limits chunk; the unchanged error taxonomy in `errors.py`.
- Produces (Tasks 3–4 rely on these exact names):
  - `Serializer(limits: SerializationLimits, handlers: tuple[JsonableHandler, ...] = ())` with method `to_jsonable(x: Any) -> Any`
  - `ConversionContext` with attributes `depth: int`, `path: JsonPath` and method `convert(child: Any, key: str | int | None = None) -> Any`
  - `type JsonableHandler = Callable[[Any, ConversionContext], JsonableHandle]`
  - `type JsonableHandle = tuple[bool, Any]`

- [ ] **Step 1: Rewrite the handler contract tests (they define the new API)**

Replace the entire contents of `tests/test_handler_registration.py` with:

```python
"""Contract tests for the consumer handler API."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dr_serialize import (
    ConversionContext,
    JsonableHandle,
    MaxDepthExceededError,
    SerializationLimits,
    Serializer,
    ValueTransformError,
    detail_repr,
    postgres_jsonb_limits,
    preview_repr,
)

DEFAULT_LIMITS = postgres_jsonb_limits()


class Marker:
    def __init__(self, tag: str) -> None:
        self.tag = tag


class Wrapper:
    def __init__(self, inner: Any) -> None:
        self.inner = inner


def marker_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if isinstance(x, Marker):
        return True, {"marker": x.tag}
    return False, None


def wrapper_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, Wrapper):
        return True, {"inner": ctx.convert(x.inner, "inner")}
    return False, None


def test_handler_intercepts_before_fallbacks() -> None:
    # Without the handler, Marker falls through to the __dict__ walk.
    plain = Serializer(limits=DEFAULT_LIMITS)
    assert plain.to_jsonable(Marker("t")) == {"tag": "t"}

    with_handler = Serializer(
        limits=DEFAULT_LIMITS, handlers=(marker_handler,)
    )
    assert with_handler.to_jsonable(Marker("t")) == {"marker": "t"}


def test_serializers_do_not_share_handlers() -> None:
    with_handler = Serializer(
        limits=DEFAULT_LIMITS, handlers=(marker_handler,)
    )
    plain = Serializer(limits=DEFAULT_LIMITS)
    assert with_handler.to_jsonable(Marker("t")) == {"marker": "t"}
    assert plain.to_jsonable(Marker("t")) == {"tag": "t"}


def test_scalars_bypass_consumer_handlers() -> None:
    def greedy(x: Any, ctx: ConversionContext) -> JsonableHandle:
        del ctx
        return True, f"intercepted {x!r}"

    serializer = Serializer(limits=DEFAULT_LIMITS, handlers=(greedy,))
    assert serializer.to_jsonable(42) == 42
    assert serializer.to_jsonable([1, 2]) == [1, 2]


def test_handler_recurses_via_ctx_convert() -> None:
    serializer = Serializer(
        limits=DEFAULT_LIMITS, handlers=(wrapper_handler,)
    )
    result = serializer.to_jsonable(Wrapper(Marker("deep")))
    assert result == {"inner": {"tag": "deep"}}


def test_ctx_convert_enforces_max_depth() -> None:
    value: Any = "leaf"
    for _ in range(5):
        value = Wrapper(value)
    limits = SerializationLimits(max_depth=3, max_bytes=1_000_000)
    serializer = Serializer(limits=limits, handlers=(wrapper_handler,))
    with pytest.raises(MaxDepthExceededError):
        serializer.to_jsonable(value)


def test_value_transform_error_subclass_carries_prefix_and_shape() -> None:
    class CustomTransformError(ValueTransformError):
        message_prefix: ClassVar[str] = "custom transform failed"

    def failing_handler(x: Any, ctx: ConversionContext) -> JsonableHandle:
        if isinstance(x, Marker):
            underlying = RuntimeError("boom")
            raise CustomTransformError(
                path=ctx.path,
                underlying=underlying,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            )
        return False, None

    serializer = Serializer(
        limits=DEFAULT_LIMITS, handlers=(failing_handler,)
    )
    with pytest.raises(CustomTransformError) as exc_info:
        serializer.to_jsonable({"k": Marker("t")})
    exc = exc_info.value
    assert str(exc) == "custom transform failed at path ('k',)"
    assert set(exc.diagnostics()) == {
        "path",
        "detail",
        "value_preview",
        "underlying",
    }
    assert exc.diagnostics()["path"] == ["k"]
```

Deliberate contract changes vs the old file: no `isolated_registry` fixture (isolation is by construction), no idempotency test (no registry to double-register into), plus the two new spec-pinned contracts (`test_serializers_do_not_share_handlers`, `test_ctx_convert_enforces_max_depth`).

- [ ] **Step 2: Run the new contract tests to verify they fail**

Run: `uv run pytest tests/test_handler_registration.py -v`
Expected: FAIL at import time with `ImportError: cannot import name 'ConversionContext' from 'dr_serialize'`

- [ ] **Step 3: Create `src/dr_serialize/_encoding.py`**

```python
"""Shared text-encoding constant for JSON byte measurement and digests."""

TEXT_ENCODING = "utf-8"
```

- [ ] **Step 4: Rewrite `src/dr_serialize/serialization.py`**

Replace the entire file with:

```python
"""JSON-safe conversion engine with an ordered, pluggable handler chain.

A :class:`Serializer` bundles limits with a tuple of consumer handlers.
Consumer handlers run after the built-in scalar/container handlers and
before the fallback handlers (plain types, Pydantic models, generators,
``__dict__`` walks), so a consumer handler can intercept any
non-primitive value. Handlers recurse via
:meth:`ConversionContext.convert`, which owns depth and path bookkeeping.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pydantic

from dr_serialize._encoding import TEXT_ENCODING
from dr_serialize.errors import (
    DEBUG_DETAIL_LIMIT,
    JsonEncodeError,
    JsonPath,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationError,
    detail_repr,
    preview_repr,
)
from dr_serialize.limits import SerializationLimits

ENCODED_PREVIEW_SLICE = 8192

type JsonableHandle = tuple[bool, Any]
type JsonableHandler = Callable[[Any, ConversionContext], JsonableHandle]

_JSON_LEAF_TYPES = (type(None), bool, int, float, str)
_JSON_CONTAINER_TYPES = (*_JSON_LEAF_TYPES, dict, list)


@dataclass(frozen=True, slots=True)
class ConversionContext:
    """Per-node conversion state handed to handlers.

    ``path`` locates the current value for error construction.
    :meth:`convert` recurses into children; depth and path bookkeeping
    is owned by the library, not the handler.
    """

    serializer: Serializer
    depth: int
    path: JsonPath

    def convert(self, child: Any, key: str | int | None = None) -> Any:
        child_path = self.path if key is None else (*self.path, key)
        return _convert_node(self.serializer, child, self.depth + 1, child_path)


@dataclass(frozen=True, slots=True)
class Serializer:
    """JSON-safe converter: limits plus an ordered consumer-handler chain."""

    limits: SerializationLimits
    handlers: tuple[JsonableHandler, ...] = ()

    def to_jsonable(self, x: Any) -> Any:
        """Convert ``x`` to a JSON-safe value, enforcing ``self.limits``."""
        value = _convert_node(self, x, 0, ())
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except TypeError as error:
            failure_path, leaf = _find_non_jsonable_path(value)
            raise JsonEncodeError(
                path=failure_path,
                type_name=type(leaf).__name__,
                detail=detail_repr(leaf),
                underlying=error,
                value_preview=preview_repr(x),
            ) from error
        size_bytes = len(encoded.encode(TEXT_ENCODING))
        if size_bytes > self.limits.max_bytes:
            preview_head, preview_tail, detail = _encoded_preview_slices(
                encoded
            )
            raise PayloadTooLargeError(
                size_bytes=size_bytes,
                max_bytes=self.limits.max_bytes,
                postgres_max_bytes=self.limits.effective_hard_max_bytes,
                path=(),
                top_level_sizes=_top_level_key_sizes(value),
                preview_head=preview_head,
                preview_tail=preview_tail,
                detail=detail,
            )
        return value


def _convert_node(
    serializer: Serializer, x: Any, depth: int, path: JsonPath
) -> Any:
    if depth > serializer.limits.max_depth:
        raise MaxDepthExceededError(
            depth=depth,
            max_depth=serializer.limits.max_depth,
            path=path,
            value_preview=preview_repr(x),
            detail=detail_repr(x),
        )
    ctx = ConversionContext(serializer=serializer, depth=depth, path=path)
    for handler in (
        *_PRIMARY_HANDLERS,
        *serializer.handlers,
        *_FALLBACK_HANDLERS,
    ):
        handled, value = handler(x, ctx)
        if handled:
            return value
    return x


def _encoded_preview_slices(encoded: str) -> tuple[str, str, str]:
    head = encoded[:ENCODED_PREVIEW_SLICE]
    if len(encoded) > ENCODED_PREVIEW_SLICE:
        tail = encoded[-ENCODED_PREVIEW_SLICE:]
    else:
        tail = ""
    detail = f"head:\n{head}"
    if tail:
        detail = f"{detail}\n\ntail:\n{tail}"
    if len(detail) > DEBUG_DETAIL_LIMIT:
        detail = detail[:DEBUG_DETAIL_LIMIT]
    return head, tail, detail


def _top_level_key_sizes(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): len(json.dumps(item, ensure_ascii=False).encode())
        for key, item in value.items()
    }


def _find_non_jsonable_path(  # noqa: PLR0911 -- exhaustive leaf walk
    value: Any,
    path: JsonPath = (),
) -> tuple[JsonPath, Any]:
    if isinstance(value, _JSON_LEAF_TYPES):
        return path, value
    if isinstance(value, dict):
        for key, item in value.items():
            sub_path = (*path, str(key))
            if not isinstance(item, _JSON_CONTAINER_TYPES):
                return sub_path, item
            found_path, leaf = _find_non_jsonable_path(item, sub_path)
            if not isinstance(leaf, _JSON_LEAF_TYPES):
                return found_path, leaf
        return path, value
    if isinstance(value, list):
        for index, item in enumerate(value):
            sub_path = (*path, index)
            if not isinstance(item, _JSON_CONTAINER_TYPES):
                return sub_path, item
            found_path, leaf = _find_non_jsonable_path(item, sub_path)
            if not isinstance(leaf, _JSON_LEAF_TYPES):
                return found_path, leaf
        return path, value
    return path, value


def _jsonable_scalar(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if x is None or isinstance(x, (bool, int, float, str)):
        return True, x
    return False, None


def _jsonable_sequence(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, (list, tuple, set, frozenset)):
        return True, [
            ctx.convert(item, index) for index, item in enumerate(x)
        ]
    return False, None


def _jsonable_mapping(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, dict):
        return True, {
            str(key): ctx.convert(item, str(key)) for key, item in x.items()
        }
    return False, None


def _jsonable_bytes(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if isinstance(x, bytes):
        return True, f"<bytes len={len(x)}>"
    return False, None


def _jsonable_type(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    if not isinstance(x, type):
        return False, None
    return True, f"<class {x.__module__}.{x.__name__}>"


def _jsonable_pydantic_model(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    if isinstance(x, pydantic.BaseModel):
        try:
            return True, x.model_dump(mode="json")
        except Exception as error:
            raise ModelDumpError(
                path=ctx.path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
    return False, None


def _jsonable_async_or_generator(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    del ctx
    if (
        inspect.iscoroutine(x)
        or inspect.isasyncgen(x)
        or inspect.isgenerator(x)
    ):
        return True, f"<{type(x).__name__}>"
    return False, None


def _jsonable_object_vars(x: Any, ctx: ConversionContext) -> JsonableHandle:
    if hasattr(x, "__dict__") and not callable(x):
        try:
            return True, {
                key: ctx.convert(value, key)
                for key, value in vars(x).items()
            }
        except SerializationError:
            raise
        except Exception as error:
            raise ObjectVarsSerializationError(
                path=ctx.path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
    return False, None


_PRIMARY_HANDLERS: tuple[JsonableHandler, ...] = (
    _jsonable_scalar,
    _jsonable_sequence,
    _jsonable_mapping,
    _jsonable_bytes,
)

_FALLBACK_HANDLERS: tuple[JsonableHandler, ...] = (
    _jsonable_type,
    _jsonable_pydantic_model,
    _jsonable_async_or_generator,
    _jsonable_object_vars,
)
```

Everything deleted relative to the old file: the module docstring's registration story, `contextvars` import, `_ACTIVE_MAX_DEPTH`, `_check_max_depth`, `_registered_handlers`, `register_handler`, `registered_handlers`, `clear_registered_handlers`, `convert_value`, `to_jsonable` (module function), `to_metadata_dict`, and the local `DEBUG_DETAIL_LIMIT`/`TEXT_ENCODING` definitions (now imported).

- [ ] **Step 5: Update `hashing.py` and rewrite `__init__.py`**

In `src/dr_serialize/hashing.py`, replace the line `TEXT_ENCODING = "utf-8"` with an import (placed with the other imports):

```python
from dr_serialize._encoding import TEXT_ENCODING
```

Replace the entire contents of `src/dr_serialize/__init__.py` with:

```python
"""Canonical hashing and JSON-safe serialization.

Public surface: canonical JSON + digests (:mod:`dr_serialize.hashing`),
the instance-based conversion engine with pluggable handlers
(:mod:`dr_serialize.serialization`), explicit limits presets
(:mod:`dr_serialize.limits`), and the typed error taxonomy
(:mod:`dr_serialize.errors`).
"""

from dr_serialize.errors import (
    JsonEncodeError,
    JsonPath,
    MaxDepthExceededError,
    ModelDumpError,
    ObjectVarsSerializationError,
    PayloadTooLargeError,
    SerializationError,
    ValueTransformError,
    detail_repr,
    preview_repr,
)
from dr_serialize.hashing import canonical_json, sha256_json_digest
from dr_serialize.limits import (
    POSTGRES_JSONB_MAX_BYTES,
    POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
    SerializationLimits,
    postgres_jsonb_limits,
)
from dr_serialize.serialization import (
    ConversionContext,
    JsonableHandle,
    JsonableHandler,
    Serializer,
)

__all__ = [
    "POSTGRES_JSONB_MAX_BYTES",
    "POSTGRES_JSONB_PAYLOAD_MAX_BYTES",
    "ConversionContext",
    "JsonEncodeError",
    "JsonPath",
    "JsonableHandle",
    "JsonableHandler",
    "MaxDepthExceededError",
    "ModelDumpError",
    "ObjectVarsSerializationError",
    "PayloadTooLargeError",
    "SerializationError",
    "SerializationLimits",
    "Serializer",
    "ValueTransformError",
    "canonical_json",
    "detail_repr",
    "postgres_jsonb_limits",
    "preview_repr",
    "sha256_json_digest",
]
```

- [ ] **Step 6: Port `tests/support.py` and `tests/test_serialization.py`**

In `tests/support.py`, change the dr_serialize import block and `assert_to_jsonable`, and add a function-style adapter so the ~40 existing test call sites stay terse:

```python
from dr_serialize import (
    SerializationError,
    SerializationLimits,
    Serializer,
    postgres_jsonb_limits,
)
```

```python
def to_jsonable(value: Any, *, limits: SerializationLimits) -> Any:
    """Function-style adapter over Serializer for terse test call sites."""
    return Serializer(limits=limits).to_jsonable(value)


def assert_to_jsonable(
    value: Any,
    *,
    limits: SerializationLimits | None = None,
) -> Any:
    result = to_jsonable(value, limits=limits or postgres_jsonb_limits())
    assert_json_dumps(result)
    assert_only_json_types(result)
    return result
```

In `tests/test_serialization.py`:
1. In the `from dr_serialize import (...)` block: remove `to_jsonable`, `to_metadata_dict`, and `serialization` if present as names being removed; keep the rest. (If any remaining test references `serialization.<something>` that no longer exists, that test is in the deleted set below.)
2. Add `to_jsonable` to the existing `from tests.support import (...)` block.
3. Delete the three `to_metadata_dict` tests in `TestMetadataAndEdgePaths`: `test_to_metadata_dict_passthrough_dict_on_serialization_error`, `test_to_metadata_dict_returns_empty_for_non_dict_failure`, `test_to_metadata_dict_wraps_scalar_success`. Keep the rest of the class.
4. Every other test call site (`to_jsonable(x, limits=...)`) now resolves to the support adapter and needs no edit.

- [ ] **Step 7: Run the full suite and lint**

Run: `uv run pytest`
Expected: PASS (63 tests: 65 minus the 3 deleted `to_metadata_dict` tests, plus a net +1 in the rewritten handler contract file). If `test_all_serialization_errors_implement_diagnostics` fails because it enumerated error classes via the `serialization` module import, point it at `dr_serialize.errors` instead — the taxonomy itself is unchanged.

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 8: Update the knowledge graph and commit**

```bash
graphify update .
git add -A
git commit -m "Replace global registry and ContextVar with instance-based Serializer"
```

### Task 2: Finalize dr-serialize and produce the merged SHA

**Files:**
- Modify: none new (verification + release mechanics)

**Interfaces:**
- Produces: a merged `main` SHA, referred to as `<MERGED_SHA>` in Tasks 3–4.

- [ ] **Step 1: Full verification from a clean tree**

```bash
git status --short   # expect empty
uv run pytest
uv run ruff check .
```
Expected: clean tree, all tests pass, lint clean.

- [ ] **Step 2: Confirm the public surface is exactly the 20-name contract**

```bash
uv run python -c "import dr_serialize; names = sorted(dr_serialize.__all__); print(len(names)); print('\n'.join(names))"
```
Expected: `20` and exactly the names from Task 1 Step 5's `__all__`.

- [ ] **Step 3: Push and open a PR**

```bash
git push -u origin serializer-instance-refactor
gh pr create --title "Instance-based Serializer refactor" --body "Implements docs/superpowers/specs/2026-07-08-serializer-instance-refactor-design.md: frozen SerializationLimits, instance-based Serializer/ConversionContext, global registry and ContextVar removed, export surface 29 -> 20."
```

- [ ] **Step 4: STOP — user merges the PR**

Wait for the user to review and merge. Then record the merged main SHA:

```bash
git checkout main && git pull && git rev-parse HEAD
```
This value is `<MERGED_SHA>` for Tasks 3–4.

### Task 3: Migrate dr-platform (Codex-delegable, parallel with Task 4)

**Repo:** `/Users/daniellerothermel/drotherm/repos/dr-platform` — create branch `dr-serialize-instance-api` from `main`.

**Files:**
- Modify: `pyproject.toml:54` (rev pin)
- Modify: `src/dr_platform/records.py:20-21,49`
- Test: existing suite (`uv run pytest`) — no test-file changes expected; `tests/test_items.py` uses only `sha256_json_digest`, which is unchanged.

**Interfaces:**
- Consumes: `Serializer`, `postgres_jsonb_limits` from dr-serialize at `<MERGED_SHA>`.

- [ ] **Step 1: Bump the pin and sync**

In `pyproject.toml` change the dr-serialize source line to:

```toml
dr-serialize = { git = "https://github.com/danielle-rothermel/dr-serialize", rev = "<MERGED_SHA>" }
```

Run: `uv lock --upgrade-package dr-serialize && uv sync`

- [ ] **Step 2: Run tests to see the expected breakage**

Run: `uv run pytest`
Expected: FAIL — `ImportError: cannot import name 'to_jsonable' from 'dr_serialize'` (from `records.py`).

- [ ] **Step 3: Port `records.py`**

Change the import block (lines 20–21 area):

```python
from dr_serialize import Serializer, postgres_jsonb_limits
```

Change the call site at line 49 from:

```python
to_jsonable(value, limits=postgres_jsonb_limits(max_bytes))
```

to:

```python
Serializer(limits=postgres_jsonb_limits(max_bytes)).to_jsonable(value)
```

(Also drop `SerializationError`/`POSTGRES_JSONB_PAYLOAD_MAX_BYTES` from the import block only if they become unused — check with ruff; they are likely still used elsewhere in the file.)

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest` — Expected: PASS
Run: `uv run ruff check .` — Expected: clean

```bash
git add -A && git commit -m "Migrate to dr-serialize instance-based Serializer API"
```

### Task 4: Migrate whetstone-ai (Codex-delegable, parallel with Task 3)

**Repo:** `/Users/daniellerothermel/drotherm/repos/whetstone-ai` — create branch `dr-serialize-instance-api` from `main`.

**Files:**
- Modify: `pyproject.toml:47` (rev pin)
- Modify: `src/whetstone/dspy_serialization.py` (handler signatures + `DSPY_HANDLERS` + `dspy_serializer`; delete `register_dspy_handlers`)
- Modify: `src/whetstone/__init__.py:7,9` (delete import-time registration)
- Modify: `src/whetstone/records/limits.py:8-9,32`
- Modify: `src/whetstone/eval_failures/recording.py:20-21,37`
- Modify: `tests/serialization_support.py:13,45-46`
- Modify: `tests/test_dspy_serialization.py`

**Interfaces:**
- Consumes: `Serializer`, `ConversionContext`, `JsonableHandle`, `JsonableHandler`, `postgres_jsonb_limits` from dr-serialize at `<MERGED_SHA>`.
- Produces: `DSPY_HANDLERS: tuple[JsonableHandler, ...]` and `dspy_serializer(max_bytes: int | None = None) -> Serializer` in `whetstone.dspy_serialization` (used by `records/limits.py`, `eval_failures/recording.py`, and tests).

- [ ] **Step 1: Bump the pin and sync**

In `pyproject.toml` change the dr-serialize source line to:

```toml
dr-serialize = { git = "https://github.com/danielle-rothermel/dr-serialize", rev = "<MERGED_SHA>" }
```

Run: `uv lock --upgrade-package dr-serialize && uv sync`

- [ ] **Step 2: Run tests to see the expected breakage**

Run: `uv run pytest`
Expected: FAIL — `ImportError: cannot import name 'convert_value' from 'dr_serialize'` (from `dspy_serialization.py`, triggered by the package `__init__`).

- [ ] **Step 3: Rewrite `dspy_serialization.py` to the ctx contract**

Replace the module's dr_serialize import block with:

```python
from dr_serialize import (
    ConversionContext,
    JsonableHandle,
    JsonableHandler,
    JsonPath,
    SerializationError,
    Serializer,
    ValueTransformError,
    detail_repr,
    postgres_jsonb_limits,
    preview_repr,
)
```

Rewrite the three handlers to take `(x, ctx)` — bodies otherwise unchanged:

```python
def jsonable_dspy_example(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    try:
        dspy = _dspy_module()
    except ImportError:
        return False, None
    if isinstance(x, dspy.Example):
        try:
            return True, ctx.convert(x.toDict())
        except SerializationError:
            raise
        except Exception as error:
            raise ExampleSerializationError(
                path=ctx.path,
                underlying=error,
                value_preview=preview_repr(x),
                detail=detail_repr(x),
            ) from error
    return False, None


def jsonable_dspy_signature_type(
    x: Any, ctx: ConversionContext
) -> JsonableHandle:
    if not isinstance(x, type):
        return False, None
    try:
        dspy = _dspy_module()
        if issubclass(x, dspy.Signature):
            return True, _signature_summary(x, ctx.path)
    except ImportError:
        pass
    except TypeError:
        pass
    return False, None


def jsonable_dspy_lm(x: Any, ctx: ConversionContext) -> JsonableHandle:
    del ctx
    try:
        dspy = _dspy_module()
    except ImportError:
        return False, None
    if isinstance(x, dspy.BaseLM):
        # Lazy: importing whetstone.lm at module top would break the
        # graph/lm isolation contract (see tests/test_graph_imports.py).
        from whetstone.lm.utils import sanitize_lm_kwargs

        return True, {
            "_kind": "BaseLM",
            "class": f"{type(x).__module__}.{type(x).__name__}",
            "model": getattr(x, "model", None),
            "kwargs": sanitize_lm_kwargs(getattr(x, "kwargs", {})),
        }
    return False, None
```

Note: `ctx.convert(x.toDict())` with no key reproduces the old `convert_value(x.toDict(), depth + 1, path)` exactly — depth + 1, same path.

Replace `register_dspy_handlers()` at the bottom of the module with:

```python
DSPY_HANDLERS: tuple[JsonableHandler, ...] = (
    jsonable_dspy_example,
    jsonable_dspy_signature_type,
    jsonable_dspy_lm,
)


def dspy_serializer(max_bytes: int | None = None) -> Serializer:
    """Serializer with whetstone's DSPy handlers installed."""
    if max_bytes is None:
        limits = postgres_jsonb_limits()
    else:
        limits = postgres_jsonb_limits(max_bytes)
    return Serializer(limits=limits, handlers=DSPY_HANDLERS)
```

Update the module docstring's first paragraph to say the handlers are installed via `dspy_serializer` / `DSPY_HANDLERS` rather than registered at import.

- [ ] **Step 4: Delete the import-time registration**

In `src/whetstone/__init__.py` delete both lines:

```python
from whetstone.dspy_serialization import register_dspy_handlers
register_dspy_handlers()
```

- [ ] **Step 5: Port the call sites**

`src/whetstone/records/limits.py` — replace the dr_serialize import of `postgres_jsonb_limits, to_jsonable` with:

```python
from whetstone.dspy_serialization import dspy_serializer
```

and change line 32 from `to_jsonable(value, limits=postgres_jsonb_limits(max_bytes))` to:

```python
dspy_serializer(max_bytes).to_jsonable(value)
```

`src/whetstone/eval_failures/recording.py` — same transform: drop `postgres_jsonb_limits, to_jsonable` from the dr_serialize import (keep the other names), add the `dspy_serializer` import, and change line 37 to `dspy_serializer(max_bytes).to_jsonable(value)`.

`tests/serialization_support.py` — replace `from dr_serialize import postgres_jsonb_limits, to_jsonable` with `from whetstone.dspy_serialization import dspy_serializer` and change `assert_to_jsonable` line 46 to `result = dspy_serializer().to_jsonable(value)`.

- [ ] **Step 6: Port `tests/test_dspy_serialization.py`**

- Replace `postgres_jsonb_limits, registered_handlers, to_jsonable` imports from dr_serialize with `from whetstone.dspy_serialization import DSPY_HANDLERS, dspy_serializer` (keep other dr_serialize names the file imports).
- Replace `DEFAULT_LIMITS = postgres_jsonb_limits()` with `DEFAULT_SERIALIZER = dspy_serializer()`.
- The test around line 45 asserting `registered_handlers()` contains the three handlers becomes an assertion on the tuple:

```python
def test_dspy_handlers_tuple_contents() -> None:
    assert DSPY_HANDLERS == (
        dspy_serialization.jsonable_dspy_example,
        dspy_serialization.jsonable_dspy_signature_type,
        dspy_serialization.jsonable_dspy_lm,
    )
```

- Delete the idempotency test (lines ~52–54, `register_dspy_handlers()` twice) — there is no registry.
- Replace remaining `to_jsonable(<value>, limits=DEFAULT_LIMITS)` calls (lines ~98, ~129) with `DEFAULT_SERIALIZER.to_jsonable(<value>)`.

- [ ] **Step 7: Verify and commit**

Run: `uv run pytest` — Expected: PASS (one fewer test: the deleted idempotency test)
Run: `uv run ruff check .` — Expected: clean

```bash
git add -A && git commit -m "Migrate to dr-serialize instance-based Serializer API"
```

### Task 5: Cross-repo verification and PRs

- [ ] **Step 1: Golden digests confirm hashing is untouched**

```bash
cd /Users/daniellerothermel/drotherm/repos/dr-graph && uv run pytest tests/test_golden_digests.py -v
cd /Users/daniellerothermel/drotherm/repos/whetstone-ai && uv run pytest tests/test_records_contracts.py -v
```
Expected: PASS without any changes to dr-graph (it uses only the unchanged hashing surface and pins an older rev — passing proves no accidental behavior drift; bumping dr-graph's pin is optional and can ride a future change).

- [ ] **Step 2: Open consumer PRs**

```bash
cd /Users/daniellerothermel/drotherm/repos/dr-platform && git push -u origin dr-serialize-instance-api && gh pr create --title "Migrate to dr-serialize instance-based Serializer API" --body "Companion to dr-serialize instance refactor (rev <MERGED_SHA>)."
cd /Users/daniellerothermel/drotherm/repos/whetstone-ai && git push -u origin dr-serialize-instance-api && gh pr create --title "Migrate to dr-serialize instance-based Serializer API" --body "Companion to dr-serialize instance refactor (rev <MERGED_SHA>)."
```

- [ ] **Step 3: Report** — summarize test counts and PR links for the user.
