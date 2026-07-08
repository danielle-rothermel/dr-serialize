# dr-serialize

JSON-safe serialization and canonical hashing for Python, built as **two
deliberately separate lanes**:

```text
                normalization lane (policy)
Any value --> Serializer.to_jsonable(...) --> Jsonable value
                                                   |
                identity lane (deterministic)      v
              canonical_json(...) --> stable text --> sha256_json_digest(...)
```

- The **normalization lane** is *policy*: it decides what your objects
  become as JSON-safe data - extensible via handlers, bounded by explicit
  limits, lossy where it must be.
- The **identity lane** is *deterministic*: it encodes already-JSON-safe
  data as canonical text and fingerprints it - no handlers, no limits,
  same input, same bytes, forever.

They compose at your call site, so identity never silently depends on
serialization policy:

```python
digest = sha256_json_digest(serializer.to_jsonable(value))
```

## Normalization: `Serializer`

```python
from dr_serialize import Serializer, postgres_jsonb_limits

serializer = Serializer(limits=postgres_jsonb_limits())
payload = serializer.to_jsonable(anything)   # JSON-safe, size- and depth-checked
```

A `Serializer` bundles `SerializationLimits` with an ordered tuple of
handlers. Built-in handlers cover scalars, sequences, mappings, bytes,
types, Pydantic models, coroutines/generators, and `__dict__` objects.
Your handlers run after the scalar/container built-ins and before the
fallbacks, so they can intercept any non-primitive value:

```python
from dr_serialize import ConversionContext, JsonableHandle, Serializer, postgres_jsonb_limits

def jsonable_point(x: object, ctx: ConversionContext) -> JsonableHandle:
    if isinstance(x, Point):
        return True, {"x": ctx.convert(x.x, "x"), "y": ctx.convert(x.y, "y")}
    return False, None      # fall through to the next handler

serializer = Serializer(limits=postgres_jsonb_limits(), handlers=(jsonable_point,))
```

Handlers recurse through `ctx.convert(child, key)` - the library owns
depth and path bookkeeping, and the configured `max_depth` is enforced
through handler recursion too.

### Limits

`SerializationLimits` (frozen) carries `max_depth`, `max_bytes`, and
`hard_max_bytes`. `postgres_jsonb_limits(max_bytes=...)` is the shipped
preset for Postgres JSONB storage; construct your own for other ceilings.
`to_jsonable` requires limits explicitly - every call site states its
storage policy.

## Identity: `canonical_json` and `sha256_json_digest`

```python
from dr_serialize import canonical_json, sha256_json_digest

text = canonical_json(payload)                     # sorted keys, compact, NaN rejected
key  = sha256_json_digest(payload, length=16)      # truncated hex digest
```

Both take `Jsonable` input - data that is already JSON-safe, typically
the output of `Serializer.to_jsonable` or values you construct yourself.
This lane is intentionally policy-free: digests are long-lived identity
keys, so they must never change because a handler was added or a limit
tuned. If you need conversion first, compose the lanes explicitly.

## Errors

Both lanes raise from one typed taxonomy rooted at `SerializationError`,
and every error carries the path to the offending value plus a
`diagnostics()` dict safe to persist:

| Error | Raised by |
| --- | --- |
| `MaxDepthExceededError` | engine: nesting exceeded `max_depth` |
| `JsonEncodeError` | engine probe and canonical lane: value not JSON-encodable (canonical also rejects NaN/inf) |
| `PayloadTooLargeError` | engine: encoded size exceeded `max_bytes` |
| `ModelDumpError` | engine: Pydantic `model_dump` failed |
| `ObjectVarsSerializationError` | engine: `__dict__` walk failed |
| `ValueTransformError` | base for consumer handler failures - subclass it with a `message_prefix` |

## API surface

Normalization: `Serializer`, `ConversionContext`, `JsonableHandler`,
`JsonableHandle`, `SerializationLimits`, `postgres_jsonb_limits`,
`POSTGRES_JSONB_PAYLOAD_MAX_BYTES`, `POSTGRES_JSONB_MAX_BYTES`.
Identity: `canonical_json`, `sha256_json_digest`.
Boundary type: `Jsonable`.
Errors: the taxonomy above plus `JsonPath`, `preview_repr`, `detail_repr`.
