# dr-serialize

[![CI](https://github.com/danielle-rothermel/dr-serialize/actions/workflows/ci.yml/badge.svg)](https://github.com/danielle-rothermel/dr-serialize/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dr-serialize.svg)](https://pypi.org/project/dr-serialize/)

| [Repo Definitions](https://danielle-rothermel.github.io/dr-serialize/) |
| --- |

**dr-serialize makes Python values JSON-safe and produces deterministic JSON
text, bytes, hashes, and identities.** Its functionality is organized into
these areas:

- **Normalization** converts Python values into JSON-safe data through bounded,
  extensible conversion rules for diagnostics and storage.
- **Canonical JSON text and hashing** render finite strict JSON values as
  deterministic text and exact UTF-8 bytes, project unordered collections into
  stable arrays, and produce validated SHA-256 digests.
- **Strict decoding** parses one complete UTF-8 JSON value under explicit byte
  and depth limits while rejecting duplicate keys, non-finite numbers, and
  malformed or trailing input.
- **Identity documents and hashes** validate a fixed document shape around a
  domain-owned payload and derive stable canonical bytes and a full identity
  hash without applying normalization policy.
- **Boundary types and diagnostics** define strict JSON values, validated
  digests, typed errors, bounded diagnostic metadata, and the shared terms and
  behavioral contracts for the package.
