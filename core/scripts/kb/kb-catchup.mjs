/**
 * kb-catchup — solo/POC mode: find knowledge-layer work after pulling
 * teammates' changes, when the team does NOT yet maintain cards.
 *
 * Keeps a personal baseline marker in .git/ (never committed, never shared).
 * Report mode diffs baseline...HEAD, maps changed files to their owning
 * cards, and lists the cards whose code changed without a card update in
 * the same range — i.e. exactly the knowledge debt your teammates left.
 * Detection is fully deterministic: ZERO tokens. Updating card content is
 * the only step that may involve AI (or your own editor).
 *
 * Usage:
 *   node scripts/kb/kb-catchup.mjs          # report stale cards since the baseline
 *   node scripts/kb/kb-catchup.mjs --mark   # set baseline = current HEAD (run AFTER reviewing)
 *
 * Typical loop:  git pull → kb:catchup → (fix flagged cards → kb:index) → kb:catchup --mark
 */

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { loadCards, buildClaims, ownerOf, REPO_ROOT, fail } from "./lib.mjs";

function git(...args) {
  return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" }).trim();
}

let gitDir;
try {
  gitDir = path.resolve(REPO_ROOT, git("rev-parse", "--git-dir"));
} catch {
  fail(["kb-catchup needs a git repository"]);
}
const MARKER = path.join(gitDir, "kb-last-sync");
const head = git("rev-parse", "HEAD");

if (process.argv.includes("--mark")) {
  fs.writeFileSync(MARKER, `${head}\n`);
  console.log(`kb-catchup: baseline set to ${head.slice(0, 10)} — future reports cover changes after this commit`);
  process.exit(0);
}

if (!fs.existsSync(MARKER)) {
  console.log("kb-catchup: no baseline yet.");
  console.log("Run `node scripts/kb/kb-catchup.mjs --mark` at a point where the cards are true (e.g. right now, after reviewing them).");
  process.exit(0);
}
const baseline = fs.readFileSync(MARKER, "utf8").trim();
try {
  git("cat-file", "-e", `${baseline}^{commit}`);
} catch {
  fail([`baseline ${baseline.slice(0, 10)} no longer exists (rebase/gc?) — re-run with --mark to set a new one`]);
}
if (baseline === head) {
  console.log(`kb-catchup: baseline is current HEAD (${head.slice(0, 10)}) — nothing to catch up`);
  process.exit(0);
}

const changed = git("diff", "--name-only", `${baseline}...${head}`)
  .split("\n")
  .map((line) => line.trim())
  .filter(Boolean);

const { cards, errors } = loadCards();
if (errors.length > 0) fail([...errors, "fix card parse errors (kb-validate) first"]);
const claims = buildClaims(cards);
const byId = new Map(cards.map((c) => [c.id, c]));

const touched = new Map(); // card id → changed files
const changedCardFiles = new Set(changed.filter((f) => f.startsWith("docs/cards/")));
for (const file of changed) {
  const owner = ownerOf(file, claims);
  if (owner) {
    if (!touched.has(owner)) touched.set(owner, []);
    touched.get(owner).push(file);
  }
}
const stale = [...touched.entries()].filter(([id]) => !changedCardFiles.has(byId.get(id).file));

console.log(`kb-catchup: ${changed.length} file(s) changed in ${baseline.slice(0, 10)}...${head.slice(0, 10)}`);
if (stale.length === 0) {
  console.log("No card-owned code changed without its card. Knowledge layer looks current for this range.");
  console.log("Optional deeper checks: `npm run kb:validate && npm run kb:drift`. Then: `npm run kb:catchup -- --mark`.");
  process.exit(0);
}

console.log(`\n${stale.length} card(s) may be stale — teammates changed their code without touching the card:\n`);
for (const [id, files] of stale) {
  console.log(`- ${byId.get(id).file} (${id})`);
  for (const f of files.sort()) console.log(`    ${f}`);
}
console.log(`
Next steps (only the flagged cards, only this range — keep it cheap):
 1. Skim the diff:      git diff ${baseline.slice(0, 10)}...HEAD -- <files above>
 2. Update the card(s): by hand (free), or in Copilot chat: /sync-cards
    with the file list above (small, card-scoped token cost).
 3. Regenerate + check: npm run kb:index && npm run kb:validate && npm run kb:drift
 4. Move the baseline:  npm run kb:catchup -- --mark
`);
process.exit(0);
