# dr-serialize

JSON-safe serialization and canonical hashing for Python: **two
deliberately separate lanes** - a policy-driven normalization lane and a
strict identity lane - plus general-purpose Canonical JSON Text utilities:

```text
                normalization lane (policy)
Any value --> Serializer.to_jsonable(...) --> diagnostic normalized JSON value
                                                   |
                canonical JSON text (deterministic) v
 canonical_json(...) --> stable text --> canonical_json_bytes(...) --> json_hash(...)

                identity lane (strict, policy-free)
Raw mapping --> IdentityDocument --> canonical_identity_json --> identity_document_hash
```

- The **normalization lane** is *policy*: it decides what your objects
  become as a diagnostic normalized JSON value - extensible via handlers,
  bounded by explicit limits, lossy where it must be.
- The **Canonical JSON Text** utilities are *deterministic*: they encode
  finite strict JSON data as canonical JSON text, exact UTF-8 bytes, and
  hashes - no handlers, no limits, same input, same bytes, forever.
- The **identity lane** is *strict*: it validates a strict JSON value and
  the exact Identity Document shape, then hashes the canonical identity JSON
  text's UTF-8 bytes - no coercion, and a diagnostic normalized JSON value
  never feeds it.

The [terms and contracts reference](https://danielle-rothermel.github.io/dr-serialize/)
renders the authoritative vocabulary in `.defs/terms.toml` and binding
behavioral rules in `.defs/contracts.toml`, including term categories,
relationships, definitions, and mappings to exported names.

Normalization and canonical JSON text generation compose at your call site,
so hashes never silently depend on serialization policy:

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

## Canonical JSON Text: text, bytes, and hashes

```python
from dr_serialize import canonical_json, canonical_json_bytes, json_hash

text = canonical_json(payload)              # profile-v1 deterministic text
data = canonical_json_bytes(payload)        # exact UTF-8 encoding of text
digest = json_hash(payload)                 # validated full Sha256Digest
display = json_hash(payload, length=16)     # ordinary truncated string
```

All three functions are bound to the **dr-serialize Canonical JSON Text
profile v1**: object keys are sorted, list order is preserved, separators are
compact, non-ASCII characters are escaped, and input must be a finite strict
JSON value at runtime (including string-only object keys and no reference
cycles). This is not RFC 8785. An incompatible profile requires a separately
named API; these functions have no profile or version parameter.

Inputs are `Jsonable` values, typically the output of
`Serializer.to_jsonable` or values you construct yourself. These utilities
are intentionally policy-free: hashes are long-lived keys, so they must never
change because a handler was added or a limit tuned. If you need conversion
first, compose with the normalization lane explicitly.

### Deterministic arrays from unordered collections

`canonical_json` preserves array order by design, so an array built from a
`set` cannot be repaired afterwards. `canonical_sorted_values` orders
already-JSON-safe values by their canonical JSON text instead, projecting a
logically unordered collection into one deterministic array. `Serializer`
applies it to every `set` and `frozenset` it normalizes; call it directly
wherever else an unordered collection becomes JSON - notably in a Pydantic
`field_serializer`, so `model_dump(mode="json")` is byte-stable:

```python
import pydantic
from dr_serialize import Jsonable, canonical_sorted_values

class Capabilities(pydantic.BaseModel):
    tags: frozenset[str]

    @pydantic.field_serializer("tags")
    def serialize_tags(self, value: frozenset[str]) -> list[Jsonable]:
        return canonical_sorted_values(value)
```

The order is arbitrary-but-stable lexicographic order over canonical JSON
text, not a human collation: `10` sorts before `2` and `true` sorts after
every number. The helper is policy-free - it never normalizes, coerces, or
deduplicates, duplicates survive, and the iterable is consumed once - and it
must never be used to reorder a semantically ordered array. Members outside
strict `Jsonable` raise `JsonEncodeError` with the member's input index
prefixed onto the error path.

`Sha256Digest` is the nominal boundary for full SHA-256 values. Its
`parse()` method accepts exactly 64 lowercase hexadecimal characters and
raises `Sha256DigestError` for prefixes, alternate case, whitespace,
truncation, or other malformed values. It also provides a strict Pydantic
core schema, so `TypeAdapter(Sha256Digest)` and model fields preserve the
nominal type, serialize as JSON strings, and publish the exact length and
lowercase-hex pattern in JSON Schema.

## Bounded strict JSON decoding

`decode_strict_json_bytes` consumes one complete UTF-8 JSON value under
mandatory byte and structural-depth limits:

```python
from dr_serialize import decode_strict_json_bytes

value = decode_strict_json_bytes(
    frame_bytes,
    max_bytes=len(frame_bytes),
    max_depth=32,
)
```

The decoder is strict and non-coercing. It rejects byte-order marks,
invalid UTF-8, duplicate decoded object keys, non-finite numbers,
malformed or trailing input, and multiple root values. Its iterative
structural parser enforces `max_depth` without depending on Python
recursion. Typed failures expose only bounded structural metadata, do not echo
or retain input, and are safe to persist. This guarantee covers exception
messages, `diagnostics()`, and chained causes/contexts. Traceback locals are
the exception: tooling that captures them can retain function arguments, so do
not persist traceback locals from secret-bearing decode calls.

## Identity lane: Identity Document and `identity_document_hash`

The identity lane is the strict, policy-free path for cross-repo domain
identity: validate a strict JSON value, wrap it in the exact three-field
[Identity Document](https://danielle-rothermel.github.io/dr-serialize/#term-identity-document)
`{schema, schema_version, payload}`, render its
[Canonical Identity JSON Text](https://danielle-rothermel.github.io/dr-serialize/#term-canonical-identity-json-text),
and hash that text's UTF-8 bytes into the full
[Identity Hash](https://danielle-rothermel.github.io/dr-serialize/#term-identity-hash). The
[terms and contracts reference](https://danielle-rothermel.github.io/dr-serialize/) defines each term;
the owning domain chooses the schema, version, and complete payload -
dr-serialize only validates.

```python
from dr_serialize import (
    build_identity_document,
    canonical_identity_json_bytes,
    identity_document_hash,
)

doc = build_identity_document(
    schema="example.config",       # the owning domain chooses this
    schema_version=1,              # ...and this
    payload={"identity_field": "value"},  # ...and the complete payload
)
h = identity_document_hash(doc)    # full 64-char lowercase SHA-256 hex
wire = canonical_identity_json_bytes(doc)  # the exact bytes h covers
```

`IdentityDocument` owns a private snapshot of its payload. Both its public
`payload` property and `to_json_dict()` return fresh deep-copied ordinary JSON
values, so mutating any caller-visible alias cannot change its canonical bytes
or hash.

Rejections are typed: `StrictJsonError` for values that are not strict JSON
values, `IdentityDocumentError` for documents that are not the exact
three-field shape. There is no truncation parameter on this path;
`identity_hash_prefix` is a separate, display-only helper that never
establishes identity. A diagnostic normalized JSON value never feeds
identity hashing. Committed golden vectors live in
`tests/fixtures/identity_golden.json` for dependent repos to reuse.

## Errors

Both lanes and the Canonical JSON Text utilities raise from one typed taxonomy
rooted at `SerializationError`. Outside the strict decoder, diagnostics are
structurally persistable and their preview and detail fields are bounded, but
they may contain payload-derived data or an underlying exception's `repr` and
are not secret-safe. Every error carries the path to the offending value plus
a `diagnostics()` dict:

| Error | Raised by |
| --- | --- |
| `MaxDepthExceededError` | engine: nesting exceeded `max_depth` |
| `JsonEncodeError` | engine probe and canonical JSON text: value not JSON-encodable (canonical requires finite strict JSON input) |
| `PayloadTooLargeError` | engine: encoded size exceeded `max_bytes` |
| `ModelDumpError` | engine: Pydantic `model_dump` failed |
| `ObjectVarsSerializationError` | engine: `__dict__` walk failed |
| `ValueTransformError` | base for consumer handler failures - subclass it with a `message_prefix` |
| `StrictJsonError` | identity lane: value is not a strict JSON value (non-JSON, non-string key, NaN/inf, cycle) |
| `IdentityDocumentError` | identity lane: document is not the exact three-field shape |
| `StrictJsonDecodeError` | base for strict bytes-first decoding failures |
| `JsonByteLimitError` | decoder: encoded input exceeds `max_bytes` |
| `JsonDepthLimitError` | decoder: nesting exceeds `max_depth` |
| `InvalidUtf8Error` | decoder: input is not strict UTF-8 |
| `JsonSyntaxError` | decoder: malformed, incomplete, or trailing JSON |
| `DuplicateJsonKeyError` | decoder: an object repeats a decoded key |
| `NonFiniteJsonNumberError` | decoder: input contains a non-finite number |

`Sha256Digest.parse()` raises `Sha256DigestError`, a `ValueError`, for a
malformed full digest.

## API surface

Normalization: `Serializer`, `ConversionContext`, `JsonableHandler`,
`JsonableHandle`, `SerializationLimits`, `postgres_jsonb_limits`,
`POSTGRES_JSONB_PAYLOAD_MAX_BYTES`, `POSTGRES_JSONB_MAX_BYTES`.
Canonical JSON Text: `canonical_json`, `canonical_json_bytes`,
`canonical_sorted_values`, `json_hash`, `Sha256Digest`, `Sha256DigestError`.
Strict decoding: `decode_strict_json_bytes`, `StrictJsonDecodeError`,
`JsonByteLimitError`, `JsonDepthLimitError`, `InvalidUtf8Error`,
`JsonSyntaxError`, `DuplicateJsonKeyError`, `NonFiniteJsonNumberError`.
Identity lane: `validate_strict_json`, `IdentityDocument`,
`build_identity_document`, `validate_identity_document`,
`canonical_identity_json`, `canonical_identity_json_bytes`,
`identity_document_hash`, `compute_identity_hash`, `identity_hash_prefix`,
`IDENTITY_DOCUMENT_FIELDS`.
Boundary type: `Jsonable`.
Errors: the taxonomy above plus `JsonPath`, `preview_repr`, `detail_repr`.
