# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Public constants `CANONICAL_JSON_MAX_CONTAINER_DEPTH` and
  `CANONICAL_JSON_MAX_INTEGER_DIGITS` for the frozen Canonical JSON Text
  profile v1 bounds.

### Changed

- Enforce the profile's 100-container and 640-decimal-digit bounds across
  canonical and identity entry points.
- Validate arbitrary-depth strict JSON iteratively while preserving failure
  paths, and keep typed errors intact when diagnostic rendering fails.
- Validate the deep-copied identity payload before storing it.

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
- Clarify that strict decoder messages, structured diagnostics, and exception
  cause and context are bounded and do not echo or retain input; traceback
  locals are outside that guarantee. Other serialization diagnostics may
  contain payload-derived or underlying-exception data.
- Bound canonical text, bytes, and hashes to the documented
  `dr-serialize Canonical JSON Text profile v1`, with runtime rejection of
  values outside finite strict JSON before encoding.
- Normalize `set` and `frozenset` values that reach `Serializer`'s built-in
  unordered-set handler deterministically: members are converted and ordered
  by canonical JSON text, so that handler's normalized output is
  byte-identical across processes regardless of `PYTHONHASHSEED`. Model or
  consumer conversions to lists erase unordered provenance and must apply
  `canonical_sorted_values` at that boundary. Lists and tuples retain their
  original order, and non-finite numbers inside a directly handled set are
  rejected with `JsonEncodeError` even though normalization still passes them
  through elsewhere.
- Apply `copy.deepcopy` to an `IdentityDocument` payload during construction
  and public payload access. Accepted custom container subclasses control
  whether the deep-copy protocol yields alias isolation.

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
