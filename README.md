# dr-serialize

JSON-safe serialization and canonical hashing for Python: **two
deliberately separate lanes** - a policy-driven normalization lane and a
strict identity lane - plus general-purpose canonical JSON utilities:

```text
                normalization lane (policy)
Any value --> Serializer.to_jsonable(...) --> diagnostic normalized JSON
                                                   |
                canonical JSON (deterministic)     v
              canonical_json(...) --> stable text --> json_hash(...)

                identity lane (strict, policy-free)
Raw mapping --> IdentityDocument --> canonical_identity_json --> identity_document_hash
```

- The **normalization lane** is *policy*: it decides what your objects
  become as diagnostic normalized JSON - extensible via handlers, bounded
  by explicit limits, lossy where it must be.
- The **canonical JSON** utilities are *deterministic*: they encode
  already-JSON-safe data as canonical text and hashes - no handlers, no
  limits, same input, same bytes, forever.
- The **identity lane** is *strict*: it validates strict JSON and the
  exact Identity Document shape, then hashes the canonical bytes - no
  coercion, and diagnostic normalized JSON never feeds it.

The vocabulary sheet at [`.defs/vocab.html`](.defs/vocab.html) is the
authoritative statement of the identity contract this repo implements:
the terms, the guarantees, what is in and out of scope, and the mapping
from each term to the exported names.

Normalization and canonical JSON compose at your call site, so hashes
never silently depend on serialization policy:

```python
hash_value = json_hash(serializer.to_jsonable(value))
```

## Ecosystem

`dr-serialize` provides serialization/schema utilities shared across the
dr-* stack: JSON-safe conversion, explicit limits, and canonical hashing.
Neighbor repos are `dr-providers`, `dr-graph`, `dr-platform`, `dr-code`,
`whetstone-ai`, and `unitbench`.
This repo depends directly on `pydantic` and no named ecosystem neighbor;
no consumer repo is declared here, though tests document extraction lineage
from `whetstone-ai`.

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

## Canonical JSON: `canonical_json` and `json_hash`

```python
from dr_serialize import canonical_json, json_hash

text = canonical_json(payload)                     # sorted keys, compact, NaN rejected
key  = json_hash(payload, length=16)               # truncated hex hash
```

Both take `Jsonable` input - data that is already JSON-safe, typically
the output of `Serializer.to_jsonable` or values you construct yourself.
These utilities are intentionally policy-free: hashes are long-lived
keys, so they must never change because a handler was added or a limit
tuned. If you need conversion first, compose with the normalization lane
explicitly.

## Identity lane: Identity Document and `identity_document_hash`

The identity lane is the strict, policy-free path for cross-repo domain
identity: validate strict JSON, wrap it in the exact three-field
[Identity Document](.defs/vocab.html#term-identity-document)
`{schema, schema_version, payload}`, render its
[Canonical Identity JSON](.defs/vocab.html#term-canonical-identity-json),
and hash the canonical bytes into the full
[Identity Hash](.defs/vocab.html#term-identity-hash). The
[vocabulary sheet](.defs/vocab.html) defines each term and the guarantees
that bind this lane; the owning domain chooses the schema, version, and
complete payload - dr-serialize only validates.

```python
from dr_serialize import build_identity_document, identity_document_hash

doc = build_identity_document(
    schema="example.config",       # the owning domain chooses this
    schema_version=1,              # ...and this
    payload={"identity_field": "value"},  # ...and the complete payload
)
h = identity_document_hash(doc)    # full 64-char lowercase SHA-256 hex
```

Rejections are typed: `StrictJsonError` for values that are not strict
JSON, `IdentityDocumentError` for documents that are not the exact
three-field shape. There is no truncation parameter on this path;
`identity_hash_prefix` is a separate, display-only helper that never
establishes identity. Diagnostic normalized JSON never feeds identity
hashing. Committed golden vectors live in
`tests/fixtures/identity_golden.json` for dependent repos to reuse.

## Errors

Both lanes and the canonical JSON utilities raise from one typed
taxonomy rooted at `SerializationError`,
and every error carries the path to the offending value plus a
`diagnostics()` dict safe to persist:

| Error | Raised by |
| --- | --- |
| `MaxDepthExceededError` | engine: nesting exceeded `max_depth` |
| `JsonEncodeError` | engine probe and canonical JSON: value not JSON-encodable (canonical also rejects NaN/inf) |
| `PayloadTooLargeError` | engine: encoded size exceeded `max_bytes` |
| `ModelDumpError` | engine: Pydantic `model_dump` failed |
| `ObjectVarsSerializationError` | engine: `__dict__` walk failed |
| `ValueTransformError` | base for consumer handler failures - subclass it with a `message_prefix` |
| `StrictJsonError` | identity lane: value is not strict JSON (non-JSON, non-string key, NaN/inf, cycle) |
| `IdentityDocumentError` | identity lane: document is not the exact three-field shape |

## API surface

Normalization: `Serializer`, `ConversionContext`, `JsonableHandler`,
`JsonableHandle`, `SerializationLimits`, `postgres_jsonb_limits`,
`POSTGRES_JSONB_PAYLOAD_MAX_BYTES`, `POSTGRES_JSONB_MAX_BYTES`.
Canonical JSON: `canonical_json`, `json_hash`.
Identity lane: `validate_strict_json`, `IdentityDocument`,
`build_identity_document`, `validate_identity_document`,
`canonical_identity_json`, `identity_document_hash`, `compute_identity_hash`,
`identity_hash_prefix`, `IDENTITY_DOCUMENT_FIELDS`.
Boundary type: `Jsonable`.
Errors: the taxonomy above plus `JsonPath`, `preview_repr`, `detail_repr`.
