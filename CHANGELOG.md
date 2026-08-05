# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.2] - 2026-08-05

### Added

- Public constants `CANONICAL_JSON_MAX_CONTAINER_DEPTH` and
  `CANONICAL_JSON_MAX_INTEGER_DIGITS` for the frozen Canonical JSON Text
  profile v1 bounds.

### Changed

- Organize the implementation and test suite by functional area under
  `_core`, `normalization`, `canonical`, `decoding`, and `identity`, while
  preserving every previously exported root name.
- Freeze the canonical and identity maximum container depth at 200 and the
  maximum integer length at 640 decimal digits.
- Default normalization to a maximum depth of 200 while preserving explicit
  per-instance configuration.
- Validate arbitrary-depth strict JSON iteratively while preserving
  first-failure paths, and keep typed serialization errors intact when
  caller-defined value or path representations fail.
- Make the public canonical callable annotations resolvable at runtime.
- Validate both the caller-provided identity payload and the deep-copied value
  that is stored by `IdentityDocument`.
- Replace the status-oriented README with a functional public-contract
  overview, update the package description, and align the terms, contracts,
  and five architecture diagrams with all 47 root exports.
- Clarify the strict decoder disclosure boundary, direct unordered-set
  determinism boundary, and `IdentityDocument` deep-copy protocol without
  claiming stronger guarantees than the runtime provides.
- Include cross-process hash-seed determinism tests in the default `pytest`
  selection.

### Removed

- Remove the former flat implementation modules `dr_serialize.digests`,
  `dr_serialize.errors`, `dr_serialize.jsonable`, `dr_serialize.limits`, and
  `dr_serialize.serialization`; import supported names from `dr_serialize` or
  their functional-area packages.

## [0.1.1] - 2026-08-05

### Added

- Exact UTF-8 byte access for canonical JSON and Canonical Identity JSON.
- Bounded bytes-first strict JSON decoding with typed, non-echoing failures
  for byte and depth limits, invalid UTF-8, malformed input, duplicate keys,
  and non-finite numbers.
- `canonical_sorted_values`, a policy-free primitive that orders
  already-JSON-safe values by their canonical JSON text, projecting a
  logically unordered collection into one deterministic JSON array while
  preserving duplicates.
- The nominal `Sha256Digest` validation boundary for full lowercase SHA-256
  values; full canonical and identity hashes now return this string subtype
  without changing their values, and strict Pydantic fields preserve it.

### Changed

- Reject negative serialization limits and configurations where `max_bytes`
  exceeds the optional `hard_max_bytes` diagnostic ceiling.
- Validate consumer handler results as already-normalized JSON values,
  preserving valid values while enforcing their shape and depth.
- Clarify that strict decoder diagnostics are bounded, non-echoing, and safe
  to persist except for traceback locals, while other serialization
  diagnostics may contain payload-derived or underlying-exception data.
- Bound canonical text, bytes, and hashes to the documented
  `dr-serialize Canonical JSON Text profile v1`, with runtime rejection of
  values outside finite strict JSON before encoding.
- Normalize `set` and `frozenset` deterministically: members are converted
  through the handler chain and then ordered by canonical JSON text, so a
  set's normalized JSON is byte-identical across processes regardless of
  `PYTHONHASHSEED`. Lists and tuples still retain their original order, and
  non-finite numbers inside a set are now rejected with `JsonEncodeError`
  even though normalization still passes them through elsewhere.
- Made `IdentityDocument` own its payload privately; every public payload or
  document mapping is now a fresh deep copy, so caller mutation cannot change
  canonical identity bytes or hashes.

## [0.1.0] - 2026-07-24

Initial release.

### Added

- Normalization lane: `Serializer.to_jsonable` with an ordered, pluggable
  handler chain and explicit `SerializationLimits` (including the
  `postgres_jsonb_limits` preset).
- Canonical JSON Text utilities: `canonical_json` and `json_hash` for
  deterministic text and SHA-256 hashes over already-JSON-safe values.
- Identity lane (`dr_serialize.identity`): `validate_strict_json`, the
  exact three-field `IdentityDocument`, `canonical_identity_json`, the
  full `identity_document_hash` / `compute_identity_hash`, and the
  display-only `identity_hash_prefix`.
- Typed error taxonomy rooted at `SerializationError`, with JsonPath
  locations on every error.
- Committed golden vectors (`tests/fixtures/hashing_golden.json`,
  `tests/fixtures/identity_golden.json`) as the cross-repository
  acceptance gate.
- Vocabulary sheet defining the identity contract, published at
  <https://danielle-rothermel.github.io/dr-serialize/>.
