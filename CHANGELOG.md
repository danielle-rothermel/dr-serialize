# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-07-24

Initial release.

### Added

- Normalization lane: `Serializer.to_jsonable` with an ordered, pluggable
  handler chain and explicit `SerializationLimits` (including the
  `postgres_jsonb_limits` preset).
- Canonical JSON utilities: `canonical_json` and `json_hash` for
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
