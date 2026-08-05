// Client-side renderer for the dr-serialize .defs terms reference.
//
// terms.toml is authoritative. This module derives reverse relationship links
// in the browser and never stores a second copy of term data.

import { parse } from "./smol-toml.js";

const RELATIONSHIPS = [
  ["is_a", "Is a"],
  ["part_of", "Part of"],
  ["specializedBy", "Specialized by"],
  ["hasParts", "Has parts"],
];

function el(tag, className, children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children ?? []) node.append(child);
  return node;
}

function titleCase(value) {
  return value.replace(/\b[\p{L}\p{N}]/gu, (character) =>
    character.toLocaleUpperCase(),
  );
}

function termId(name) {
  return `term-${name.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

function termLink(name, text = titleCase(name)) {
  const link = el("a", null, [text]);
  link.href = `#${termId(name)}`;
  return link;
}

function validateTerms(terms) {
  if (!Array.isArray(terms)) throw new Error("terms.toml must contain a terms array");

  const names = new Set();
  const foldedNames = new Set();
  for (const term of terms) {
    if (typeof term.name !== "string" || !term.name.trim()) {
      throw new Error("every term must have a non-blank name");
    }
    if (typeof term.definition !== "string" || !term.definition.trim()) {
      throw new Error(`${term.name}: definition must be non-blank`);
    }
    const folded = term.name.toLocaleLowerCase();
    if (names.has(term.name) || foldedNames.has(folded)) {
      throw new Error(`duplicate term name: ${term.name}`);
    }
    names.add(term.name);
    foldedNames.add(folded);
  }

  for (const term of terms) {
    for (const field of ["is_a", "part_of"]) {
      for (const target of term[field] ?? []) {
        if (!names.has(target)) {
          throw new Error(`${term.name}: ${field} target does not exist: ${target}`);
        }
      }
    }
  }
}

function deriveReverseRelationships(terms) {
  const reverse = new Map(
    terms.map((term) => [term.name, { specializedBy: [], hasParts: [] }]),
  );
  for (const term of terms) {
    for (const target of term.is_a ?? []) {
      reverse.get(target).specializedBy.push(term.name);
    }
    for (const target of term.part_of ?? []) {
      reverse.get(target).hasParts.push(term.name);
    }
  }
  return reverse;
}

function relationshipAwareOrder(terms) {
  const sourceIndex = new Map(terms.map((term, index) => [term.name, index]));
  const predecessors = new Map(terms.map((term) => [term.name, new Set()]));
  const children = new Map(terms.map((term) => [term.name, new Set()]));

  for (const term of terms) {
    for (const parent of [...(term.is_a ?? []), ...(term.part_of ?? [])]) {
      predecessors.get(term.name).add(parent);
      children.get(parent).add(term.name);
    }
  }

  const ordered = [];
  const visited = new Set();
  function visit(name) {
    if (visited.has(name)) return;
    if (![...predecessors.get(name)].every((parent) => visited.has(parent))) return;

    visited.add(name);
    ordered.push(terms[sourceIndex.get(name)]);
    const descendants = [...children.get(name)].sort(
      (left, right) => sourceIndex.get(left) - sourceIndex.get(right),
    );
    for (const descendant of descendants) visit(descendant);
  }

  for (const term of terms) visit(term.name);
  if (ordered.length !== terms.length) {
    const unresolved = terms
      .filter((term) => !visited.has(term.name))
      .map((term) => term.name)
      .join(", ");
    throw new Error(`relationship cycle prevents ordering: ${unresolved}`);
  }
  return ordered;
}

function relationshipBlock(label, names) {
  const values = el(
    "div",
    "relationship-values",
    names.map((name) => termLink(name)),
  );
  return el("div", "relationship", [
    el("div", "relationship-label", [label]),
    values,
  ]);
}

function definitionNodes(definition, terms) {
  const names = terms.map((term) => term.name).sort((left, right) => right.length - left.length);
  const byFoldedName = new Map(terms.map((term) => [term.name.toLocaleLowerCase(), term.name]));
  const escapedNames = names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const matcher = new RegExp(escapedNames.join("|"), "giu");
  const nodes = [];
  let cursor = 0;

  for (const match of definition.matchAll(matcher)) {
    if (match.index > cursor) nodes.push(definition.slice(cursor, match.index));
    const canonicalName = byFoldedName.get(match[0].toLocaleLowerCase());
    const link = termLink(canonicalName, match[0]);
    link.className = "vocab-ref";
    nodes.push(link);
    cursor = match.index + match[0].length;
  }
  if (cursor < definition.length) nodes.push(definition.slice(cursor));
  return nodes;
}

function termRow(term, terms, reverse) {
  const name = el("dfn", "term-name", [titleCase(term.name)]);
  name.id = termId(term.name);

  const categories = el(
    "div",
    "term-categories",
    (term.categories ?? []).map((category) => {
      const badge = el("span", "term-category", [category]);
      badge.dataset.category = category;
      return badge;
    }),
  );

  const derived = reverse.get(term.name);
  const relationshipValues = {
    is_a: term.is_a ?? [],
    part_of: term.part_of ?? [],
    specializedBy: derived.specializedBy,
    hasParts: derived.hasParts,
  };
  const relationshipBlocks = RELATIONSHIPS.flatMap(([field, label]) =>
    relationshipValues[field].length
      ? [relationshipBlock(label, relationshipValues[field])]
      : [],
  );
  const metadataChildren = [name, categories];
  if (relationshipBlocks.length) {
    metadataChildren.push(el("div", "term-relationships", relationshipBlocks));
  }

  const detailChildren = [
    el("p", "term-definition", definitionNodes(term.definition.trim(), terms)),
  ];
  if (term.exported_symbols?.length) {
    detailChildren.push(
      el("div", "term-symbols", [
        el("div", "symbols-label", ["Exported symbols"]),
        el(
          "div",
          "symbol-list",
          term.exported_symbols.map((symbol) => el("code", null, [symbol])),
        ),
      ]),
    );
  }

  return el("tr", null, [
    el("td", "term-metadata", metadataChildren),
    el("td", "term-detail", detailChildren),
  ]);
}

async function fillTermsReference(slot) {
  const response = await fetch(slot.dataset.defsFile);
  if (!response.ok) {
    throw new Error(`${slot.dataset.defsFile}: HTTP ${response.status}`);
  }
  const terms = parse(await response.text()).terms ?? [];
  validateTerms(terms);
  const reverse = deriveReverseRelationships(terms);
  const orderedTerms = relationshipAwareOrder(terms);
  slot.replaceChildren(
    ...orderedTerms.map((term) => termRow(term, terms, reverse)),
  );
}

async function fillSlot(slot) {
  slot.setAttribute("aria-busy", "true");
  try {
    if (slot.dataset.defsKind !== "terms-reference") {
      throw new Error(`unsupported defs kind: ${slot.dataset.defsKind}`);
    }
    await fillTermsReference(slot);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const cell = el("td", "defs-error", [`Failed to load terms: ${message}`]);
    cell.colSpan = 2;
    slot.replaceChildren(el("tr", null, [cell]));
  } finally {
    slot.removeAttribute("aria-busy");
  }
}

for (const slot of document.querySelectorAll("[data-defs-file]")) {
  fillSlot(slot);
}
