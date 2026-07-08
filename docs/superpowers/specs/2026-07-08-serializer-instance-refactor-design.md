# dr-serialize: Instance-Based Serializer Refactor

**Date:** 2026-07-08
**Status:** Approved design, pending implementation plan

## Motivation

The conversion engine carries two pieces of hidden process-global state:

1. `_ACTIVE_MAX_DEPTH` (a `ContextVar`): `to_jsonable` sets it, `convert_value`
   reads it ambiently. `convert_value`'s depth limit therefore depends on where
   it is called from, and `to_metadata_dict` silently runs with the ContextVar
   default rather than any configured limit.
2. `_registered_handlers` (a module-global list): every consumer in a process
   shares one registry. This forces `clear_registered_handlers` and the
   `isolated_registry` test fixtures to exist, and pushes whetstone-ai into
   import-time side-effect registration (`whetstone/__init__.py` calls
   `register_dspy_handlers()` on import).

Handler authors must also manually manage recursion bookkeeping
(`convert_value(child, depth + 1, path)`), which the library should own.

A consumer-usage audit (dr-graph, dr-platform, whetstone-ai — the only three
consumers, all in-house) found 11 of 29 exports unused, including one footgun:
`POSTGRES_JSONB_LIMITS` is a shared **mutable** module-level
`SerializationLimits` instance duplicating the `postgres_jsonb_limits()`
factory that every consumer actually uses.

## Constraints and decisions (from brainstorm)

- **Clean break approved.** No shims or compatibility layers; all three
  consumers are updated in the same sweep.
- **Trajectory: internal shared library.** Design for exactly the current
  consumers' needs; no speculative extension points.
- **Pydantic vs dataclass rule:** Pydantic where external data enters and
  mistakes must fail loudly; `@dataclass(frozen=True, slots=True)` for
  internal, behavior-light objects the type checker already protects.
  Pydantic remains a hard dependency regardless (the engine converts
  `pydantic.BaseModel` values).

## Target API surface (29 → 20 exports)

```python
# Conversion engine (serialization.py)
Serializer            # frozen slots dataclass: limits + handlers; .to_jsonable(x)
ConversionContext     # frozen slots dataclass handed to handlers; ctx.convert(child, key)
JsonableHandler       # Callable[[Any, ConversionContext], JsonableHandle]
JsonableHandle        # tuple[bool, Any] — unchanged

# Limits (limits.py)
SerializationLimits   # Pydantic BaseModel, gains frozen=True
postgres_jsonb_limits
POSTGRES_JSONB_PAYLOAD_MAX_BYTES
POSTGRES_JSONB_MAX_BYTES

# Hashing (hashing.py) — unchanged
canonical_json
sha256_json_digest

# Errors (errors.py) — taxonomy unchanged
SerializationError, JsonEncodeError, MaxDepthExceededError, ModelDumpError,
ObjectVarsSerializationError, PayloadTooLargeError, ValueTransformError,
JsonPath, preview_repr, detail_repr
```

### Removed from the public API

| Name | Reason | Fate |
| --- | --- | --- |
| `register_handler` | replaced by `Serializer(handlers=...)` | deleted |
| `registered_handlers` | same | deleted |
| `clear_registered_handlers` | isolation is free with instances | deleted |
| `convert_value` | replaced by `ctx.convert` | becomes internal walk |
| `to_metadata_dict` | zero consumers; swallows errors into `{}` | deleted (rebuild in a consumer if ever needed) |
| `POSTGRES_JSONB_LIMITS` | mutable shared instance; duplicates factory | deleted |
| `DEFAULT_MAX_DEPTH` | implementation default | module-internal |
| `DEBUG_DETAIL_LIMIT` | error-repr tuning knob | module-internal |
| `MESSAGE_PREVIEW` | error-repr tuning knob | module-internal |
| `SHA256_HEX_DIGEST_LENGTH` | no consumer imports it | module-internal |

`JsonableHandle` is kept (whetstone annotates its handlers with it).

## Serializer and ConversionContext semantics

`Serializer` is a `@dataclass(frozen=True, slots=True)`:

- Fields: `limits: SerializationLimits`, `handlers: tuple[JsonableHandler, ...] = ()`.
- `to_jsonable(x: Any) -> Any` preserves the current function's behavior
  exactly: convert, `json.dumps` probe (raising `JsonEncodeError` with the
  non-jsonable path), UTF-8 size check against `limits.max_bytes` (raising
  `PayloadTooLargeError` with top-level key sizes and previews).
- The depth limit travels through the conversion walk explicitly. The
  `_ACTIVE_MAX_DEPTH` ContextVar is deleted.

`ConversionContext` is a `@dataclass(frozen=True, slots=True)` allocated per
node visit (hot path — no Pydantic validation cost):

- Carries the owning serializer's handler chain, current `depth`, and `path`
  (exposed to handlers for error construction, matching today's contract).
- `convert(child: Any, key: str | int | None = None) -> Any` increments depth,
  extends the path with `key` when given, enforces the depth check (raising
  `MaxDepthExceededError`), and runs the full chain. The library owns the
  bookkeeping handler authors currently do by hand.

Handler contract changes from `(x, depth, path) -> JsonableHandle` to
`(x, ctx) -> JsonableHandle`. Chain order is unchanged: built-in primary
handlers (scalar, sequence, mapping, bytes), then consumer handlers in tuple
order, then built-in fallbacks (type, Pydantic model, coroutine/generator,
`__dict__` walk), then identity.

## Housekeeping riding along

- `SerializationLimits` gains `frozen=True` (mutation raises).
- `DEBUG_DETAIL_LIMIT` single-sourced in `errors.py` (currently duplicated in
  `serialization.py`).
- `TEXT_ENCODING` single-sourced privately (currently duplicated in
  `serialization.py` and `hashing.py`).

## Consumer migration (same sweep)

- **dr-graph:** uses hashing only — no change. Golden-digest tests double as
  cross-repo regression checks.
- **dr-platform** (`records.py`): module-level
  `_SERIALIZER = Serializer(limits=postgres_jsonb_limits())`; call sites
  become `_SERIALIZER.to_jsonable(x)`.
- **whetstone-ai:** `dspy_serialization.py` exports
  `DSPY_HANDLERS: tuple[JsonableHandler, ...]` instead of
  `register_dspy_handlers()`; the import-time call in
  `whetstone/__init__.py` is deleted. Its four handlers rewrite to the
  `(x, ctx)` signature — mechanical:
  `convert_value(x.toDict(), depth + 1, path)` → `ctx.convert(x.toDict())`.
  One shared `Serializer(limits=..., handlers=DSPY_HANDLERS)` lives where
  whetstone already centralizes serialization helpers. Its
  `ValueTransformError` subclasses work unchanged.
- Both repos' `isolated_registry` test fixtures are deleted; tests construct
  fresh `Serializer` instances.

## Testing

- Port existing contract tests (`test_serialization.py`,
  `test_handler_registration.py`) to the instance API — same behaviors, one
  test per contract.
- New contracts to pin:
  - Two `Serializer` instances do not share handlers.
  - `ctx.convert` enforces the configured `max_depth` through consumer-handler
    recursion.
  - `SerializationLimits` mutation raises (frozen).
- Delete `to_metadata_dict` tests with the function.

## Out of scope

- Any change to hashing behavior or the error taxonomy's diagnostics shapes
  (persisted alongside failure records; treated as frozen contracts).
- Speculative extension points (per-call handler overrides, multiple limit
  profiles per serializer, non-Postgres presets).
