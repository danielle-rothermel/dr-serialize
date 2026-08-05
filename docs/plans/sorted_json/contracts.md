# Contracts added by this plan

Additions to `.defs/contracts.toml`. No existing contracts are modified; in
particular "Canonical JSON Text follows frozen profile v1" is untouched —
canonical value ordering sits on top of the profile and does not change it.

```toml
[[contracts]]
title = "Canonical value ordering is policy-free and duplicate-preserving"
statement = """
canonical_sorted_values() orders already-JSON-safe values by their Canonical \
JSON Text profile v1 representation. It never normalizes, coerces, \
deduplicates, or selects domain fields; duplicates are preserved. Values \
outside strict Jsonable fail through JsonEncodeError with the failing \
member's input index prefixed onto the error path; there is no parallel \
error taxonomy. The function projects logically unordered collections into \
deterministic JSON arrays and is never used to reorder semantically ordered \
arrays."""
rationale = """
A single policy-free ordering primitive lets any producer of unordered \
collections -- including downstream Pydantic field serializers -- reach \
deterministic JSON without dr-serialize taking on normalization policy or a \
second error taxonomy."""
date = "2026-08-05"
check = "uv run pytest -q tests/test_canonical.py -k canonical_sorted_values"
terms = ["canonical value ordering", "canonicalization", "strict JSON value"]

[[contracts]]
title = "Set normalization is deterministic"
statement = """
Serializer converts set and frozenset members recursively through the \
handler chain, then orders the converted members with \
canonical_sorted_values(), so the normalized JSON of a set is byte-identical \
across fresh processes regardless of PYTHONHASHSEED. Lists and tuples \
always retain their original order. There is no compatibility path and no \
configurable ordering policy. Non-finite numbers inside sets are rejected \
through canonical JSON error behavior even though normalization passes them \
through elsewhere."""
rationale = """
Hash iteration order is the only nondeterminism in the normalization lane's \
container handling; ordering set members by canonical JSON text removes it \
at the source, since canonical_json() intentionally preserves array order \
and cannot repair it downstream."""
date = "2026-08-05"
check = "uv run pytest -q tests/test_serialization.py -k 'set or frozenset'"
terms = ["normalization", "canonical value ordering"]
```
