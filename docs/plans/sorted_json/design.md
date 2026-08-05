# Deterministic set normalization and `canonical_sorted_values`

## Problem

`Serializer` routes list, tuple, set, and frozenset through one sequence
handler (`_jsonable_sequence`), so set and frozenset members are emitted in
Python hash iteration order. Their normalized JSON can differ across fresh
processes with different `PYTHONHASHSEED` values. `canonical_json()` sorts
object keys but deliberately preserves array order, so it cannot repair a
nondeterministically constructed array afterward.

Downstream Pydantic models (e.g. frozenset fields in dr-providers) need a
public primitive usable inside a `field_serializer` to produce deterministic
`model_dump(mode="json")` output. dr-providers is not modified in this task.

## Public helper

```python
def canonical_sorted_values(values: Iterable[Jsonable], /) -> list[Jsonable]
```

- Lives in `dr_serialize/canonical.py`: the helper is deterministic and
  policy-free, consuming `Jsonable` and ordering by canonical JSON text, so
  it belongs to the canonicalization lane, not the normalization lane.
- Exported from `dr_serialize.__init__` and added to `__all__`.
- Name: `canonical_sorted_values` rather than the originally suggested
  `sorted_json_values`, tying the helper to the repo's established
  `canonical_*` vocabulary (`canonical_json`, Canonical JSON Text profile
  v1). The PR explains this choice.
- Signature matches the `canonical_json_bytes` convention (positional-only
  `/`).

### Contract

- Inputs are already JSON-safe `Jsonable` values. The helper never
  normalizes, coerces, deduplicates, or selects domain fields.
- Duplicates are preserved; the input iterable is consumed exactly once.
- Values are ordered by their `canonical_json()` text (Canonical JSON Text
  profile v1), which supports heterogeneous and nested `Jsonable` values
  without relying on Python cross-type comparability.
- Invalid values fail through the existing canonical JSON error behavior
  (`JsonEncodeError`); no parallel error taxonomy. The helper prefixes the
  failing member's input-iterable index onto the error path before
  re-raising, so failures are locatable when the helper is called on a list.
  For set-derived input the index is arbitrary but reproducible within the
  call.
- Documented purpose: projecting a logically unordered collection into a
  deterministic JSON array. It must not be used to reorder semantically
  ordered arrays.

### Ordering semantics (documented, not "fixed")

The order is arbitrary-but-stable lexicographic order over canonical JSON
text, not a human collation: `10` sorts before `2`; `true` sorts after
numbers; non-ASCII strings order by their `\uXXXX` escapes. `1` and `1.0`
produce distinct canonical texts (`"1"` vs `"1.0"`) and both survive as
duplicates-by-value, consistent with the no-dedup contract.

## Serializer changes

Split `_jsonable_sequence` into two primary handlers:

- **list/tuple**: unchanged behavior — original order retained, tuples
  become JSON arrays.
- **set/frozenset**: recursively convert every member through
  `ConversionContext.convert` (index keys in iteration order, as today),
  then order the converted `Jsonable` members with
  `canonical_sorted_values`, returning the deterministic array.

Depth, size, handler-chain, path, and diagnostic behavior are otherwise
preserved. No compatibility path and no configurable ordering policy.

Documented path caveat: set-member path indices in errors raised during
member conversion refer to iteration order, not output-array position. These
paths were already nondeterministic before this change.

## Accepted behavior changes

1. **Non-finite floats in sets now raise.** Today `json.dumps` in
   `to_jsonable` allows NaN/inf, so `{float("nan")}` normalizes to `[NaN]`.
   Routing set members through canonical ordering rejects non-finite numbers
   with `JsonEncodeError`. Accepted: this is exactly "fail through the
   existing canonical JSON error behavior," and any workaround would be a
   prohibited compatibility path. The resulting asymmetry (a NaN inside a
   list still passes normalization) is documented. Whether normalization
   should reject non-finite floats everywhere is deferred, out of scope.
2. **Unserializable hashable set members fail earlier with a different
   path.** A value that falls through every handler unconverted (e.g. a
   lambda) previously failed at `to_jsonable`'s top-level `json.dumps` with
   a root-relative path. It now fails at ordering time inside the set
   handler, with the member-local path prefixed by the member's iteration
   index. Accepted: same error type, earlier surfacing.

## Pydantic boundary

By the time `Serializer` calls `model_dump(mode="json")`, Pydantic has
erased whether an array came from a set, so `Serializer` cannot and does not
claim to repair unordered Pydantic fields automatically. The supported
downstream pattern — a `field_serializer` that projects set members to
`Jsonable` values and calls `canonical_sorted_values` — is documented in the
helper docstring, demonstrated by a test model, and shown in a short README
example. No Pydantic-specific decorators or mixins are added to
dr-serialize.

## Testing

All tests synchronize on state, never time; the subprocess timeout is a
watchdog only.

1. List and tuple order unchanged (extends existing coverage).
2. Set and frozenset normalization is deterministic — multi-element sets
   asserted against exact expected arrays (existing tests dodge this via
   single-element sets and caller-side sorting; they are strengthened).
3. Mixed and nested `Jsonable` values order by canonical JSON text, not
   native Python comparison (heterogeneous inputs that would raise
   `TypeError` under `sorted()` directly).
4. Duplicates supplied through a general iterable (including a generator)
   remain duplicated, including `1` vs `1.0` vs `True` distinctions.
5. `canonical_sorted_values` is exported (`__all__` membership + import from
   package root) and directly usable by a representative Pydantic
   `field_serializer` whose `model_dump(mode="json")` output is asserted
   byte-stable.
6. Fresh `sys.executable` subprocesses with several explicitly controlled
   `PYTHONHASHSEED` values (e.g. `0`, `1`, `4242`) produce byte-identical
   normalized JSON for a nontrivial string frozenset. Registered under a new
   `subprocess` pytest marker in `pyproject.toml`. Runtime is measured after
   implementation: if the marked tests exceed 25% of total suite wall time,
   they flip to opt-in via `addopts = "-m 'not subprocess'"`; otherwise they
   run by default with the marker available for deselection.
7. `canonical_json` continues to preserve ordinary array order.
8. Existing limits and typed-error tests continue to pass unweakened; new
   error-path tests pin the index-prefixed `JsonEncodeError` behavior for
   both the helper and the set handler (including the NaN-in-set case).

## Repo bookkeeping in the same PR

- `.defs/terms.toml`: new term entry (see `terms.md`).
- `.defs/contracts.toml`: new contract entries (see `contracts.md`);
  re-render the defs doc per the repo's render process. The existing
  "Canonical JSON Text follows frozen profile v1" contract is untouched —
  the helper sits on top of the profile and does not change it.
- Dated `CHANGELOG.md` entry.
- Docstrings and README updated forward-facing only.
