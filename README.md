# dr-serialize

[![CI](https://github.com/danielle-rothermel/dr-serialize/actions/workflows/ci.yml/badge.svg)](https://github.com/danielle-rothermel/dr-serialize/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dr-serialize.svg)](https://pypi.org/project/dr-serialize/)

| [Repo Definitions](https://danielle-rothermel.github.io/dr-serialize/) | [Terms TOML](https://github.com/danielle-rothermel/dr-serialize/blob/main/.defs/terms.toml) | [Contracts TOML](https://github.com/danielle-rothermel/dr-serialize/blob/main/.defs/contracts.toml) |
| --- | --- | --- |

**dr-serialize normalizes Python values into JSON-encodable data and produces
deterministic JSON text, bytes, hashes, and identities.** Its functionality is
organized into four areas supported by shared infrastructure:

- **[Normalization](https://github.com/danielle-rothermel/dr-serialize/tree/main/src/dr_serialize/normalization)**
  converts Python values into bounded, JSON-shaped data through extensible
  conversion rules for diagnostics and storage. Non-finite floats may survive
  normalization outside canonical set ordering.
- **[Canonical JSON](https://github.com/danielle-rothermel/dr-serialize/tree/main/src/dr_serialize/canonical)**
  renders bounded finite strict JSON values as deterministic text and exact
  UTF-8 bytes, projects unordered collections into stable arrays, and produces
  validated SHA-256 digests.
- **[Strict decoding](https://github.com/danielle-rothermel/dr-serialize/tree/main/src/dr_serialize/decoding)**
  parses one complete UTF-8 JSON value under explicit byte and depth limits
  while rejecting duplicate keys, non-finite numbers, and malformed or trailing
  input.
- **[Identity](https://github.com/danielle-rothermel/dr-serialize/tree/main/src/dr_serialize/identity)**
  validates a fixed document shape around a domain-owned payload and derives
  stable canonical bytes and a full identity hash without normalization.
- **[Infra](https://github.com/danielle-rothermel/dr-serialize/tree/main/src/dr_serialize/_core)**
  provides the contracts shared by those areas:
  - recursive JSON values and iterative strict validation;
  - validated full SHA-256 digests;
  - diagnostic paths, typed errors, and bounded metadata;
  - a common UTF-8 encoding invariant.

The declarations below are abbreviated contract shapes; `...` replaces
implementation details.

## Normalization

Normalization is policy-driven and may be lossy. A `Serializer` combines
explicit depth and size limits with an ordered chain of consumer handlers, and
produces JSON-encodable, `Jsonable`-shaped data for diagnostics or storage
rather than identity. Non-finite floats may survive normal conversion outside
canonical set ordering.

```python
class SerializationLimits(BaseModel):
    max_depth: int = 200
    max_bytes: int
    hard_max_bytes: int | None = None


def postgres_jsonb_limits(
    max_bytes: int = POSTGRES_JSONB_PAYLOAD_MAX_BYTES,
) -> SerializationLimits: ...
```

```python
type JsonableHandle = tuple[bool, Any]
type JsonableHandler = Callable[
    [Any, ConversionContext],
    JsonableHandle,
]


@dataclass(frozen=True, slots=True)
class ConversionContext:
    serializer: Serializer
    depth: int
    path: JsonPath

    def convert(
        self,
        child: Any,
        key: str | int | None = None,
    ) -> Jsonable: ...


@dataclass(frozen=True, slots=True)
class Serializer:
    limits: SerializationLimits
    handlers: tuple[JsonableHandler, ...] = ()

    def to_jsonable(self, x: Any) -> Jsonable: ...
```

## Canonical JSON

Canonical JSON consumes finite strict JSON values without applying handlers or
selecting domain fields. Profile v1 admits at most 200 nested containers and
640 decimal digits per integer; scalars have depth 0 and a root list or object
has depth 1. It then uses the standard-library JSON encoder; canonical text is
the stable contract from which exact bytes and hashes are derived.

```python
CANONICAL_JSON_MAX_CONTAINER_DEPTH: Final[int] = 200
CANONICAL_JSON_MAX_INTEGER_DIGITS: Final[int] = 640


def canonical_json(value: Jsonable) -> str: ...
def canonical_json_bytes(value: Jsonable, /) -> bytes: ...


def json_hash(
    value: Jsonable,
    *,
    length: int | None = None,
) -> Sha256Digest | str: ...
```

```python
def canonical_sorted_values(
    values: Iterable[Jsonable],
    /,
) -> list[Jsonable]: ...
```

`canonical_sorted_values` projects only logically unordered collections into a
stable array. It does not reorder arrays whose existing order is meaningful.

## Strict decoding

Strict decoding accepts exactly one bounded UTF-8 JSON value without coercion.
Failure messages, structured diagnostics, and exception cause and context do
not echo or retain input. Traceback locals are outside this guarantee.

```python
def decode_strict_json_bytes(
    data: bytes,
    /,
    *,
    max_bytes: int,
    max_depth: int,
) -> Jsonable: ...
```

```python
class StrictJsonDecodeError(SerializationError): ...


class JsonByteLimitError(StrictJsonDecodeError): ...
class JsonDepthLimitError(StrictJsonDecodeError): ...
class InvalidUtf8Error(StrictJsonDecodeError): ...
class JsonSyntaxError(StrictJsonDecodeError): ...
class DuplicateJsonKeyError(StrictJsonDecodeError): ...
class NonFiniteJsonNumberError(StrictJsonDecodeError): ...
```

## Identity

The owning domain supplies every identity-bearing fact. dr-serialize validates
the fixed document envelope against the same complete Canonical JSON Text
profile, applies `copy.deepcopy` during construction and payload access, and
derives canonical identity bytes and a full hash without normalization.
Accepted custom container subclasses control whether the deep-copy protocol
yields alias isolation.

```python
class IdentityDocument:
    schema: str
    schema_version: int

    def __init__(
        self,
        schema: str,
        schema_version: int,
        payload: Jsonable,
    ) -> None: ...

    @property
    def payload(self) -> Jsonable: ...

    def to_json_dict(self) -> dict[str, Jsonable]: ...
```

```python
def build_identity_document(
    *,
    schema: str,
    schema_version: int,
    payload: Any,
) -> IdentityDocument: ...


def validate_identity_document(
    document: dict[Any, Any],
) -> IdentityDocument: ...


def canonical_identity_json_bytes(
    document: IdentityDocument,
    /,
) -> bytes: ...


def identity_document_hash(
    document: IdentityDocument,
) -> Sha256Digest: ...
```

## Shared infrastructure

The shared infrastructure defines the recursive value, digest, and diagnostic
contracts used across the four functional areas. Finite-number validation is a
runtime property of strict `Jsonable` values because Python's type system cannot
express it in the recursive alias.

```python
type Jsonable = (
    None
    | bool
    | int
    | float
    | str
    | list[Jsonable]
    | dict[str, Jsonable]
)


def validate_strict_json(value: Any) -> Jsonable: ...
```

```python
class Sha256Digest(str):
    @classmethod
    def parse(cls, value: str, /) -> Self: ...


type JsonPath = tuple[str | int, ...]


class SerializationError(Exception):
    path: JsonPath
    detail: str

    def diagnostics(self) -> dict[str, Any]: ...
```

## Development

Install dependencies and the commit hook once per clone:

```bash
uv sync --locked
uv run pre-commit install
```

The hook runs `scripts/pre-check.sh` for Ruff formatting, Ruff lint, and type
checking, followed by the test suite.
