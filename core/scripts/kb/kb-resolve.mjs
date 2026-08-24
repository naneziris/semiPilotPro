/**
 * kb-resolve — deterministic retrieval: tags → the exact file set to read.
 *
 * Fixed traversal, same input = same output:
 *   1. cards owning any requested tag (from the closed vocabulary),
 *   2. plus one hop along depends_on AND reverse-dependents,
 *   3. plus the matched/expanded cards' linked deep docs.
 * Code paths are printed last as L3 pointers — read them only when
 * executing a task, never to "get an overview".
 *
 * This is the ONLY sanctioned retrieval mechanism for AI agents working in
 * this repo. If the resolved set looks wrong, fix the cards.
 *
 * Usage: node scripts/kb/kb-resolve.mjs --tags graphics,sync-cloud
 */

import { loadCards, loadVocabulary, fail } from "./lib.mjs";

const argIndex = process.argv.indexOf("--tags");
const rawTags = argIndex !== -1 ? process.argv[argIndex + 1] : undefined;
if (!rawTags) {
  fail(["usage: kb-resolve --tags <tag1,tag2>  (tags come from docs/cards/_vocabulary.md)"]);
}
const requested = rawTags.split(",").map((t) => t.trim()).filter(Boolean);

const vocabulary = loadVocabulary();
const unknown = requested.filter((t) => !vocabulary.has(t));
if (unknown.length > 0) {
  fail([
    `unknown tag(s): ${unknown.join(", ")}`,
    `valid tags: ${[...vocabulary].sort().join(", ")}`,
  ]);
}

const { cards, errors } = loadCards();
if (errors.length > 0) fail([...errors, "fix parse errors (run kb-validate) before resolving"]);

const byId = new Map(cards.map((c) => [c.id, c]));
const matched = new Set(
  cards.filter((c) => c.owns.some((t) => requested.includes(t))).map((c) => c.id)
);
if (matched.size === 0) fail([`no card owns any of: ${requested.join(", ")}`]);

const expanded = new Set(matched);
for (const id of matched) {
  for (const dep of byId.get(id).depends_on) expanded.add(dep);
  for (const card of cards) {
    if (card.depends_on.includes(id)) expanded.add(card.id);
  }
}

const pick = (ids) =>
  [...ids].sort().map((id) => byId.get(id)).filter(Boolean);

console.log(`# kb-resolve — tags: ${requested.join(", ")}`);
console.log(`# matched: ${[...matched].sort().join(", ")}`);
console.log(`# expanded (one hop): ${[...expanded].filter((id) => !matched.has(id)).sort().join(", ") || "(none)"}`);
console.log("\n## Read these cards (L1)");
for (const card of pick(expanded)) console.log(card.file);

const docs = new Set();
for (const card of pick(expanded)) for (const d of card.docs) docs.add(d);
console.log("\n## Deep docs if the card points you there (L2)");
if (docs.size === 0) console.log("(none)");
for (const d of [...docs].sort()) console.log(d);

console.log("\n## Code paths — execution time only (L3)");
for (const card of pick(expanded)) {
  for (const c of [...card.code].sort()) console.log(`${c}  (${card.id})`);
}
