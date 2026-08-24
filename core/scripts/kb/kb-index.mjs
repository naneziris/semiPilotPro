/**
 * kb-index — regenerate docs/cards/manifest.json from the cards.
 *
 * The manifest is the only committed generated artifact: a few KB, sorted
 * keys, changes only when cards change (so PR diffs are meaningful and it
 * never churns per merge). Everything larger is validated-and-discarded.
 *
 * Usage:
 *   node scripts/kb/kb-index.mjs           # write the manifest
 *   node scripts/kb/kb-index.mjs --check   # exit 1 if the committed file is stale
 */

import fs from "node:fs";
import { loadCards, MANIFEST_FILE, stableStringify, fail } from "./lib.mjs";

const { cards, errors } = loadCards();
if (errors.length > 0) fail([...errors, "fix parse errors (run kb-validate) before indexing"]);

const tags = {};
const cardIndex = {};
const edges = [];

for (const card of cards) {
  for (const tag of card.owns) {
    (tags[tag] ??= []).push(card.id);
  }
  cardIndex[card.id] = {
    file: card.file,
    owns: [...card.owns].sort(),
    code: [...card.code].sort(),
    docs: [...card.docs].sort(),
    depends_on: [...card.depends_on].sort(),
  };
  for (const dep of card.depends_on) edges.push([card.id, dep]);
}
for (const list of Object.values(tags)) list.sort();
edges.sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]));

const manifest = {
  $generated: "scripts/kb/kb-index.mjs — do not edit by hand",
  cards: cardIndex,
  edges,
  tags,
};
const output = stableStringify(manifest);

if (process.argv.includes("--check")) {
  const existing = fs.existsSync(MANIFEST_FILE) ? fs.readFileSync(MANIFEST_FILE, "utf8") : "";
  if (existing !== output) {
    console.error("ERROR  docs/cards/manifest.json is stale — run `npm run kb:index` and commit the result");
    process.exit(1);
  }
  console.log("kb-index: manifest up to date");
} else {
  fs.writeFileSync(MANIFEST_FILE, output);
  console.log(`kb-index: wrote docs/cards/manifest.json (${cards.length} cards, ${edges.length} edges)`);
}
