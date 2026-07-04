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
- **JSON-safe conversion engine** — best-effort `to_jsonable` /
  `to_metadata_dict` over an ordered handler chain (stdlib + Pydantic
  handlers built in) with depth and size guards.
- **Handler registration** — `register_handler` lets consumers add their
  own type handlers; registered handlers run before the generic
  fallbacks. `convert_value` is the public recursion entry point for
  handlers converting nested values.
- **Explicit limits** — `SerializationLimits` injected at the call site;
  `POSTGRES_JSONB_LIMITS` / `postgres_jsonb_limits(...)` ship as *a*
  preset, not *the* truth.
- **Typed errors** — the `SerializationError` hierarchy with
  path-to-offending-value diagnostics; consumers subclass
  `ValueTransformError` for their own handler failures.

## Usage

```python
from dr_serialize import (
    canonical_json,
    postgres_jsonb_limits,
    register_handler,
    sha256_json_digest,
    to_jsonable,
)

digest = sha256_json_digest({"b": 1, "a": 2}, length=16)
payload = to_jsonable(value, limits=postgres_jsonb_limits())
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
