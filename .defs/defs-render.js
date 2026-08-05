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

function anchorId(kind, value) {
  const slug = value
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${kind}-${slug}`;
}

function termId(name) {
  return anchorId("term", name);
}

function contractId(title) {
  return anchorId("contract", title);
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

function validateContracts(contracts, terms) {
  if (!Array.isArray(contracts)) {
    throw new Error("contracts.toml must contain a contracts array");
  }

  const termNames = new Set(terms.map((term) => term.name));
  const foldedTitles = new Set();
  for (const contract of contracts) {
    if (contract === null || typeof contract !== "object") {
      throw new Error("every contract must be a table");
    }
    for (const field of ["title", "statement", "rationale", "date"]) {
      if (typeof contract[field] !== "string" || !contract[field].trim()) {
        throw new Error(`every contract must have a non-blank ${field}`);
      }
    }
    if (
      contract.check !== undefined &&
      (typeof contract.check !== "string" || !contract.check.trim())
    ) {
      throw new Error(`${contract.title}: check must be non-blank`);
    }
    if (contract.terms !== undefined && !Array.isArray(contract.terms)) {
      throw new Error(`${contract.title}: terms must be an array`);
    }

    const foldedTitle = contract.title.toLocaleLowerCase();
    if (foldedTitles.has(foldedTitle)) {
      throw new Error(`duplicate contract title: ${contract.title}`);
    }
    foldedTitles.add(foldedTitle);

    const referencedTerms = new Set();
    for (const term of contract.terms ?? []) {
      if (referencedTerms.has(term)) {
        throw new Error(`${contract.title}: duplicate term reference: ${term}`);
      }
      if (!termNames.has(term)) {
        throw new Error(`${contract.title}: term does not exist: ${term}`);
      }
      referencedTerms.add(term);
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

function contractRow(contract) {
  const title = el("span", "contract-title", [contract.title]);
  title.id = contractId(contract.title);

  const date = el("time", "contract-date", [contract.date]);
  date.dateTime = contract.date;
  const metadataChildren = [title, date];
  if (contract.terms?.length) {
    metadataChildren.push(
      el(
        "div",
        "contract-terms",
        contract.terms.map((term) => {
          const link = termLink(term, term);
          link.className = "contract-term";
          return link;
        }),
      ),
    );
  }

  const detailChildren = [
    el("p", "contract-statement", [contract.statement.trim()]),
    el("p", "contract-rationale", [contract.rationale.trim()]),
  ];
  if (contract.check) {
    detailChildren.push(
      el("div", "contract-check", [
        el("div", "check-label", ["Check"]),
        el("code", null, [contract.check]),
      ]),
    );
  }

  return el("tr", null, [
    el("td", "contract-metadata", metadataChildren),
    el("td", "contract-detail", detailChildren),
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

async function fillContractsReference(slot) {
  const [contractsResponse, termsResponse] = await Promise.all([
    fetch(slot.dataset.defsFile),
    fetch(slot.dataset.defsTermsFile),
  ]);
  if (!contractsResponse.ok) {
    throw new Error(`${slot.dataset.defsFile}: HTTP ${contractsResponse.status}`);
  }
  if (!termsResponse.ok) {
    throw new Error(
      `${slot.dataset.defsTermsFile}: HTTP ${termsResponse.status}`,
    );
  }

  const contracts = parse(await contractsResponse.text()).contracts ?? [];
  const terms = parse(await termsResponse.text()).terms ?? [];
  validateTerms(terms);
  validateContracts(contracts, terms);
  slot.replaceChildren(...contracts.map((contract) => contractRow(contract)));
}

async function fillSlot(slot) {
  slot.setAttribute("aria-busy", "true");
  try {
    if (slot.dataset.defsKind === "terms-reference") {
      await fillTermsReference(slot);
    } else if (slot.dataset.defsKind === "contracts-reference") {
      await fillContractsReference(slot);
    } else {
      throw new Error(`unsupported defs kind: ${slot.dataset.defsKind}`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const subject =
      slot.dataset.defsKind === "contracts-reference" ? "contracts" : "terms";
    const cell = el("td", "defs-error", [
      `Failed to load ${subject}: ${message}`,
    ]);
    cell.colSpan = 2;
    slot.replaceChildren(el("tr", null, [cell]));
  } finally {
    slot.removeAttribute("aria-busy");
  }
}

for (const slot of document.querySelectorAll("[data-defs-file]")) {
  fillSlot(slot);
}
