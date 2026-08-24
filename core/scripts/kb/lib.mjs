/**
 * Shared helpers for the knowledge-layer scripts (kb-*).
 *
 * Zero dependencies on purpose: the frontmatter parser below accepts a
 * strict, documented YAML subset instead of pulling in a YAML library, so
 * the whole suite runs with plain `node` before any install step. Anything
 * outside the subset is a validation error — which is a feature: card
 * frontmatter stays machine-simple by construction.
 *
 * Supported frontmatter subset (kb-validate enforces it):
 *   key: value                 scalar (optionally "double-quoted")
 *   key: [a, b, c]             inline list (items optionally quoted)
 *   key:                       block list
 *     - item one
 *     - "item: with punctuation"
 */

import fs from "node:fs";
import path from "node:path";

export const REPO_ROOT = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  ".."
);
export const CARDS_DIR = path.join(REPO_ROOT, "docs", "cards");
export const VOCAB_FILE = path.join(CARDS_DIR, "_vocabulary.md");
export const MANIFEST_FILE = path.join(CARDS_DIR, "manifest.json");

/** Frontmatter keys a card may use. Anything else is a typo. */
export const KNOWN_KEYS = [
  "id",
  "owns",
  "depends_on",
  "public_contracts",
  "code",
  "docs",
  "invariants",
];
export const LIST_KEYS = new Set(KNOWN_KEYS.filter((k) => k !== "id"));

function unquote(raw, where) {
  const s = raw.trim();
  if (s.startsWith('"')) {
    if (!s.endsWith('"') || s.length < 2) {
      throw new Error(`${where}: unterminated quoted string: ${raw}`);
    }
    return s.slice(1, -1);
  }
  if (s.startsWith("'")) {
    throw new Error(`${where}: use double quotes, not single: ${raw}`);
  }
  return s;
}

/**
 * Parse `--- ... ---` frontmatter plus prose body from a card file's text.
 * Returns { data, body, errors } — errors are collected, not thrown, so
 * kb-validate can report all of them at once.
 */
export function parseFrontmatter(text, fileLabel) {
  const errors = [];
  const lines = text.split("\n");
  if (lines[0] !== "---") {
    return { data: {}, body: text, errors: [`${fileLabel}: no frontmatter (file must start with ---)`] };
  }
  const data = {};
  let i = 1;
  let currentListKey = null;
  for (; i < lines.length; i++) {
    const line = lines[i];
    if (line === "---") break;
    if (line.trim() === "" || line.trim().startsWith("#")) continue;
    const where = `${fileLabel}:${i + 1}`;

    const itemMatch = line.match(/^ {2}- (.*)$/);
    if (itemMatch) {
      if (!currentListKey) {
        errors.push(`${where}: list item without a preceding "key:" line`);
        continue;
      }
      try {
        data[currentListKey].push(unquote(itemMatch[1], where));
      } catch (e) {
        errors.push(e.message);
      }
      continue;
    }

    const kv = line.match(/^([A-Za-z0-9_]+):(.*)$/);
    if (!kv) {
      errors.push(`${where}: unparseable line (subset is key:value, key:[..], "  - item"): ${line}`);
      currentListKey = null;
      continue;
    }
    const key = kv[1];
    const rest = kv[2].trim();
    currentListKey = null;

    if (rest === "") {
      data[key] = [];
      currentListKey = key;
    } else if (rest.startsWith("[")) {
      if (!rest.endsWith("]")) {
        errors.push(`${where}: inline list must close on the same line`);
        continue;
      }
      const inner = rest.slice(1, -1).trim();
      try {
        data[key] =
          inner === ""
            ? []
            : inner.split(",").map((part) => unquote(part, where));
      } catch (e) {
        errors.push(e.message);
      }
    } else {
      try {
        data[key] = unquote(rest, where);
      } catch (e) {
        errors.push(e.message);
      }
    }
  }
  if (lines[i] !== "---") {
    errors.push(`${fileLabel}: frontmatter never closed with ---`);
  }
  const body = lines.slice(i + 1).join("\n").trim();
  return { data, body, errors };
}

/** Load the closed tag vocabulary. Tags are lines matching "- `tag`". */
export function loadVocabulary() {
  const text = fs.readFileSync(VOCAB_FILE, "utf8");
  const tags = new Set();
  for (const line of text.split("\n")) {
    const m = line.match(/^- `([a-z0-9-]+)`/);
    if (m) tags.add(m[1]);
  }
  return tags;
}

/** Load every card (files in docs/cards/ except _vocabulary.md / manifest). */
export function loadCards() {
  const cards = [];
  const errors = [];
  const files = fs
    .readdirSync(CARDS_DIR)
    .filter((f) => f.endsWith(".md") && !f.startsWith("_"))
    .sort();
  for (const file of files) {
    const rel = path.join("docs", "cards", file);
    const text = fs.readFileSync(path.join(CARDS_DIR, file), "utf8");
    const { data, body, errors: parseErrors } = parseFrontmatter(text, rel);
    errors.push(...parseErrors);
    for (const key of LIST_KEYS) {
      if (key in data && !Array.isArray(data[key])) {
        errors.push(`${rel}: "${key}" must be a list`);
        data[key] = [data[key]];
      }
    }
    cards.push({
      file: rel,
      lineCount: text.split("\n").length,
      id: typeof data.id === "string" ? data.id : "",
      owns: data.owns ?? [],
      depends_on: data.depends_on ?? [],
      public_contracts: data.public_contracts ?? [],
      code: data.code ?? [],
      docs: data.docs ?? [],
      invariants: data.invariants ?? [],
      unknownKeys: Object.keys(data).filter((k) => !KNOWN_KEYS.includes(k)),
      body,
    });
  }
  return { cards, errors };
}

/**
 * Normalize a card `code:`/`docs:` entry against the repo: directories get
 * a trailing "/". Returns null when the path does not exist.
 */
export function normalizeClaim(entry) {
  const abs = path.join(REPO_ROOT, entry);
  if (!fs.existsSync(abs)) return null;
  const isDir = fs.statSync(abs).isDirectory();
  if (isDir && !entry.endsWith("/")) return `${entry}/`;
  return entry;
}

/**
 * Build the file→card ownership table. Longest matching claim wins, so a
 * card may own a subtree inside another card's directory.
 */
export function buildClaims(cards) {
  const claims = [];
  for (const card of cards) {
    for (const entry of card.code) {
      const normalized = normalizeClaim(entry);
      claims.push({ path: normalized ?? entry, card: card.id, exists: normalized !== null });
    }
  }
  claims.sort((a, b) => b.path.length - a.path.length);
  return claims;
}

/** Owning card id for a repo-relative file path, or null. */
export function ownerOf(relFile, claims) {
  for (const claim of claims) {
    if (claim.path.endsWith("/") ? relFile.startsWith(claim.path) : relFile === claim.path) {
      return claim.card;
    }
  }
  return null;
}

/** JSON.stringify with recursively sorted object keys (deterministic). */
export function stableStringify(value) {
  const sortValue = (v) => {
    if (Array.isArray(v)) return v.map(sortValue);
    if (v && typeof v === "object") {
      return Object.fromEntries(
        Object.keys(v)
          .sort()
          .map((k) => [k, sortValue(v[k])])
      );
    }
    return v;
  };
  return `${JSON.stringify(sortValue(value), null, 2)}\n`;
}

export function fail(messages) {
  for (const m of messages) console.error(`ERROR  ${m}`);
  process.exit(1);
}
