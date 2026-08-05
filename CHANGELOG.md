# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
