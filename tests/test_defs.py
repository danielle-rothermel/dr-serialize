"""Semantic checks for the authoritative .defs TOML files."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

DEFS_DIR = Path(__file__).parent.parent / ".defs"


def _load_toml(name: str) -> dict[str, Any]:
    with (DEFS_DIR / name).open("rb") as file:
        return tomllib.load(file)


def _anchor(kind: str, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{kind}-{slug}"


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
