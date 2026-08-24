/**
 * kb-validate — referential-integrity check for the knowledge layer.
 *
 * Fails (exit 1) on: frontmatter outside the documented subset, unknown
 * keys, missing required keys, malformed/duplicate ids, filename/id
 * mismatch, tags outside _vocabulary.md, a tag owned by more than one
 * card, code:/docs: paths that don't exist, duplicate code claims,
 * depends_on ids that don't resolve (or self-reference), empty prose body.
 * Warns (exit 0) on cards over 80 lines.
 *
 * Usage: node scripts/kb/kb-validate.mjs
 */

import { loadCards, loadVocabulary, normalizeClaim } from "./lib.mjs";

const { cards, errors } = loadCards();
const warnings = [];
const vocabulary = loadVocabulary();

if (cards.length === 0) errors.push("no cards found in docs/cards/");
if (vocabulary.size === 0) errors.push("no tags parsed from docs/cards/_vocabulary.md");

const ids = new Map();
const tagOwners = new Map();
const claimOwners = new Map();

for (const card of cards) {
  const where = card.file;

  for (const key of card.unknownKeys) {
    errors.push(`${where}: unknown frontmatter key "${key}"`);
  }

  if (!card.id) {
    errors.push(`${where}: missing required "id"`);
  } else {
    if (!/^[a-z0-9]+(\.[a-z0-9-]+)+$/.test(card.id)) {
      errors.push(`${where}: id "${card.id}" must match <system>.<module> in lowercase kebab`);
    }
    if (ids.has(card.id)) {
      errors.push(`${where}: duplicate id "${card.id}" (also in ${ids.get(card.id)})`);
    }
    ids.set(card.id, where);
    const slug = card.id.split(".").pop();
    if (!where.endsWith(`/${slug}.md`)) {
      errors.push(`${where}: filename must be "${slug}.md" to match id "${card.id}"`);
    }
  }

  if (card.owns.length === 0) errors.push(`${where}: "owns" must list at least one tag`);
  for (const tag of card.owns) {
    if (!vocabulary.has(tag)) {
      errors.push(`${where}: tag "${tag}" is not in _vocabulary.md (closed list — add it by PR first)`);
    }
    if (tagOwners.has(tag)) {
      errors.push(`${where}: tag "${tag}" already owned by ${tagOwners.get(tag)} — one owner per tag`);
    }
    tagOwners.set(tag, card.id || where);
  }

  if (card.code.length === 0) errors.push(`${where}: "code" must list at least one path`);
  for (const entry of card.code) {
    const normalized = normalizeClaim(entry);
    if (normalized === null) {
      errors.push(`${where}: code path does not exist: ${entry}`);
      continue;
    }
    if (claimOwners.has(normalized)) {
      errors.push(`${where}: code path "${normalized}" already claimed by ${claimOwners.get(normalized)}`);
    }
    claimOwners.set(normalized, card.id || where);
  }
  for (const entry of card.docs) {
    if (normalizeClaim(entry) === null) {
      errors.push(`${where}: docs path does not exist: ${entry}`);
    }
  }

  if (!card.body) errors.push(`${where}: prose body is empty — a card is a summary, not just metadata`);
  if (card.lineCount > 80) {
    warnings.push(`${where}: ${card.lineCount} lines (>80) — split the module or push detail to docs/deep/`);
  }
}

for (const card of cards) {
  for (const dep of card.depends_on) {
    if (dep === card.id) errors.push(`${card.file}: depends_on contains itself`);
    else if (!ids.has(dep)) errors.push(`${card.file}: depends_on "${dep}" does not resolve to any card`);
  }
}

for (const tag of vocabulary) {
  if (!tagOwners.has(tag)) warnings.push(`_vocabulary.md: tag "${tag}" is owned by no card`);
}

for (const w of warnings) console.warn(`WARN   ${w}`);
if (errors.length > 0) {
  for (const e of errors) console.error(`ERROR  ${e}`);
  console.error(`\nkb-validate: ${errors.length} error(s), ${warnings.length} warning(s), ${cards.length} card(s)`);
  process.exit(1);
}
console.log(`kb-validate: OK — ${cards.length} cards, ${vocabulary.size} tags, ${warnings.length} warning(s)`);
