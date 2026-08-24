/**
 * kb-guard — staleness nag: did this change touch a card's code without
 * touching the card?
 *
 * Given a list of changed files (from `git diff --name-only`), maps each to
 * its owning card and reports cards whose code changed while their card
 * file did not. Deliberately NON-BLOCKING (always exit 0): for a small
 * team a nag builds the habit; flip to blocking by checking the output in
 * CI once the habit sticks.
 *
 * Usage:
 *   git diff --name-only origin/main...HEAD | node scripts/kb/kb-guard.mjs
 *   node scripts/kb/kb-guard.mjs --files src/lib/sync.ts docs/cards/sync-cloud.md
 */

import fs from "node:fs";
import { loadCards, buildClaims, ownerOf } from "./lib.mjs";

function readChangedFiles() {
  const flagIndex = process.argv.indexOf("--files");
  if (flagIndex !== -1) return process.argv.slice(flagIndex + 1);
  try {
    return fs
      .readFileSync(0, "utf8")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

const changed = readChangedFiles();
if (changed.length === 0) {
  console.log("kb-guard: no changed files supplied — nothing to check");
  process.exit(0);
}

const { cards, errors } = loadCards();
if (errors.length > 0) {
  // Guard must never hard-fail a PR on its own account; validate handles errors.
  console.log("kb-guard: card parse errors present — kb-validate will report them");
  process.exit(0);
}
const claims = buildClaims(cards);
const byId = new Map(cards.map((c) => [c.id, c]));

const touchedCards = new Map(); // card id → changed files under its claims
const changedCardFiles = new Set(changed.filter((f) => f.startsWith("docs/cards/")));

for (const file of changed) {
  const owner = ownerOf(file, claims);
  if (owner) (touchedCards.get(owner) ?? touchedCards.set(owner, []).get(owner)).push(file);
}

const stale = [...touchedCards.entries()].filter(
  ([id]) => !changedCardFiles.has(byId.get(id).file)
);

if (stale.length === 0) {
  console.log(`kb-guard: OK — ${touchedCards.size} card area(s) touched, all cards updated or untouched code`);
  process.exit(0);
}

const lines = [];
lines.push("kb-guard: these changes touch card-owned code without updating the card.");
lines.push("If nothing the card says changed, ignore this; otherwise update the card in this PR.");
lines.push("");
for (const [id, files] of stale) {
  lines.push(`- ${byId.get(id).file} (${id}) — code touched:`);
  for (const f of files.sort()) lines.push(`    ${f}`);
}
const report = lines.join("\n");
console.log(report);

if (process.env.GITHUB_STEP_SUMMARY) {
  fs.appendFileSync(
    process.env.GITHUB_STEP_SUMMARY,
    `### Knowledge-layer staleness check\n\n\`\`\`\n${report}\n\`\`\`\n`
  );
}
process.exit(0);
