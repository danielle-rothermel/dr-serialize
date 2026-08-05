from __future__ import annotations

import re
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

import dr_serialize

DEFS_DIR = Path(__file__).parents[2] / ".defs"
RELATIONSHIP_FIELDS = ("is_a", "part_of")


def _load_toml(name: str) -> dict[str, Any]:
    with (DEFS_DIR / name).open("rb") as file:
        return tomllib.load(file)


def _anchor(kind: str, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{kind}-{slug}"


def _relationship_edges(
    terms: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    return [
        (term["name"], relationship, target)
        for term in terms
        for relationship in RELATIONSHIP_FIELDS
        for target in term.get(relationship, [])
    ]


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    visited: set[str] = set()
    active_positions: dict[str, int] = {}
    path: list[str] = []

    def visit(name: str) -> list[str] | None:
        visited.add(name)
        active_positions[name] = len(path)
        path.append(name)

        for target in graph[name]:
            if target in active_positions:
                cycle_start = active_positions[target]
                return [*path[cycle_start:], target]
            if target not in visited:
                cycle = visit(target)
                if cycle is not None:
                    return cycle

        path.pop()
        del active_positions[name]
        return None

    for name in graph:
        if name not in visited:
            cycle = visit(name)
            if cycle is not None:
                return cycle
    return None


def test_contract_references_match_canonical_terms() -> None:
    terms = _load_toml("terms.toml")["terms"]
    contracts = _load_toml("contracts.toml")["contracts"]
    canonical_terms = {term["name"] for term in terms}

    for contract in contracts:
        referenced_terms = contract.get("terms", [])
        assert len(referenced_terms) == len(set(referenced_terms)), contract[
            "title"
        ]
        assert set(referenced_terms) <= canonical_terms, contract["title"]


def test_renderer_anchors_and_contract_titles_are_unique() -> None:
    terms = _load_toml("terms.toml")["terms"]
    contracts = _load_toml("contracts.toml")["contracts"]
    titles = [contract["title"] for contract in contracts]

    assert all(title.strip() for title in titles)
    assert len({title.casefold() for title in titles}) == len(titles)

    anchors = [
        *(_anchor("term", term["name"]) for term in terms),
        *(_anchor("contract", title) for title in titles),
    ]
    assert len(set(anchors)) == len(anchors)


def test_relationship_targets_are_canonical_terms() -> None:
    terms = _load_toml("terms.toml")["terms"]
    canonical_terms = {term["name"] for term in terms}
    missing_targets = [
        f"{source} --{relationship}--> {target}"
        for source, relationship, target in _relationship_edges(terms)
        if target not in canonical_terms
    ]

    assert not missing_targets, (
        "Relationship targets must name existing terms:\n"
        + "\n".join(missing_targets)
    )


def test_relationship_graph_is_acyclic() -> None:
    terms = _load_toml("terms.toml")["terms"]
    canonical_terms = {term["name"] for term in terms}
    edges = _relationship_edges(terms)
    self_links = [
        f"{source} --{relationship}--> {target}"
        for source, relationship, target in edges
        if source == target
    ]

    assert not self_links, (
        "Terms must not relate to themselves:\n" + "\n".join(self_links)
    )

    graph = {name: [] for name in canonical_terms}
    for source, _, target in edges:
        if target in canonical_terms:
            graph[source].append(target)

    cycle = _find_cycle(graph)
    assert cycle is None, (
        "The combined is_a/part_of relationship graph contains a cycle: "
        + " -> ".join(cycle or [])
    )


def test_exported_symbols_are_unique_and_exactly_public() -> None:
    terms = _load_toml("terms.toml")["terms"]
    symbol_terms: dict[str, list[str]] = defaultdict(list)
    for term in terms:
        for symbol in term.get("exported_symbols", []):
            symbol_terms[symbol].append(term["name"])

    duplicate_symbols = {
        symbol: names
        for symbol, names in symbol_terms.items()
        if len(names) > 1
    }
    assert not duplicate_symbols, (
        "Each exported symbol must map to exactly one term: "
        f"{duplicate_symbols}"
    )

    mapped_symbols = set(symbol_terms)
    public_symbols = set(dr_serialize.__all__)
    assert mapped_symbols == public_symbols, (
        "Exported-symbol mappings must exactly cover dr_serialize.__all__. "
        f"Unmapped public names: {sorted(public_symbols - mapped_symbols)}. "
        f"Mapped non-public names: {sorted(mapped_symbols - public_symbols)}."
    )
