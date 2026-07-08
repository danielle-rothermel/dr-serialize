# dr-serialize

Canonical JSON hashing and JSON-safe serialization with pluggable type
handlers and explicit, configurable limits.

Extracted from [whetstone-ai](https://github.com/danielle-rothermel/whetstone-ai);
the foundation package its sibling libraries depend on. Small,
dependency-light (Pydantic only), and deliberately narrow in scope.

## What it provides

- **Canonical JSON + digests** — `canonical_json` (sorted-key, compact,
  NaN-rejecting) and `sha256_json_digest` with caller-owned truncation
  lengths.
- **JSON-safe conversion engine** — best-effort `Serializer.to_jsonable`
  over an ordered handler chain (stdlib + Pydantic handlers built in)
  with depth and size guards.
- **Pluggable consumer handlers** — a `Serializer` is constructed with a
  tuple of handlers, each `(x: Any, ctx: ConversionContext) ->
  JsonableHandle`; handlers run before the generic fallbacks, return
  `(False, None)` to fall through, and recurse into children via
  `ctx.convert(child, key)`.
- **Explicit limits** — `SerializationLimits` injected at the call site;
  `postgres_jsonb_limits(...)` ships as *a* preset, not *the* truth.
- **Typed errors** — the `SerializationError` hierarchy with
  path-to-offending-value diagnostics (`.diagnostics()`); consumers
  subclass `ValueTransformError` for their own handler failures.

## Usage

```python
from dr_serialize import (
    Serializer,
    canonical_json,
    postgres_jsonb_limits,
    sha256_json_digest,
)


def my_handler(x, ctx):
    if not isinstance(x, MyType):
        return False, None
    return True, {"value": ctx.convert(x.value, "value")}


serializer = Serializer(
    limits=postgres_jsonb_limits(), handlers=(my_handler,)
)

digest = sha256_json_digest({"b": 1, "a": 2}, length=16)
payload = serializer.to_jsonable(value)
```

## Anti-goals

- No storage, DB coupling, or compression.
- Not a general utils package: additions must be about canonical
  serialization or digests and needed by at least two consumers.

## Development

```bash
uv sync
uv run pytest
uv run ruff check && uv run ty check
```
