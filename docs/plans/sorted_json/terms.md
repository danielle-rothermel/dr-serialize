# Terms added by this plan

Additions to `.defs/terms.toml`. No existing terms are modified.

```toml
[[terms]]
name = "canonical value ordering"
definition = """
The ordering of already-JSON-safe values by their Canonical JSON Text \
representation under a declared profile, projecting a logically unordered \
collection into one deterministic JSON array. It preserves duplicates, \
never normalizes, coerces, deduplicates, or selects domain fields, and is \
never applied to semantically ordered arrays."""
categories = ["canonicalization"]
exported_symbols = ["canonical_sorted_values"]
```
