/**
 * kb-drift — verify declared card edges against the REAL import graph.
 *
 * Computes the actual TypeScript/JavaScript import graph fresh (using the
 * target repo's own `typescript` package — run after installing deps),
 * folds file-level imports up to card level via each card's code: claims
 * (longest claim wins), and diffs against the declared depends_on edges.
 *
 * LANGUAGE SCOPE: this analyzer covers .ts/.tsx/.js/.jsx/.mjs via the
 * TypeScript compiler API. For repos in other languages, disable the drift
 * job (kb-validate/index/resolve/guard are language-agnostic) or replace
 * `importSpecifiers`/`resolveSpecifier` with an extractor for your stack.
 *
 * CONFIG (optional): scripts/kb/kb.config.json
 *   {
 *     "srcDirs": ["src"],                 // dirs to walk (repo-relative)
 *     "aliases": { "@/": "src/" },        // import prefix → repo-relative dir
 *     "extensions": [".ts", ".tsx"]       // file extensions to analyze
 *   }
 * Absent file = the defaults shown above.
 *
 * Output classes:
 *   DRIFT  card X imports from card Y but does not declare it   → exit 1
 *   INFO   declared edge never observed in imports (conceptual   → exit 0
 *          dependencies like a schema card are expected here)
 *   INFO   source files owned by no card
 *
 * Nothing is written to disk: the graph is generated, compared, discarded.
 *
 * Usage: node scripts/kb/kb-drift.mjs [--verbose]
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { loadCards, buildClaims, ownerOf, REPO_ROOT, fail } from "./lib.mjs";

const CONFIG_FILE = path.join(REPO_ROOT, "scripts", "kb", "kb.config.json");
const defaults = { srcDirs: ["src"], aliases: { "@/": "src/" }, extensions: [".ts", ".tsx"] };
let config = defaults;
if (fs.existsSync(CONFIG_FILE)) {
  try {
    config = { ...defaults, ...JSON.parse(fs.readFileSync(CONFIG_FILE, "utf8")) };
  } catch (e) {
    fail([`scripts/kb/kb.config.json is not valid JSON: ${e.message}`]);
  }
}

const require = createRequire(path.join(REPO_ROOT, "package.json"));
let ts;
try {
  ts = require("typescript");
} catch {
  fail(["kb-drift needs the repo's typescript package — install dev dependencies first (or disable the drift job for non-TS repos)"]);
}

const verbose = process.argv.includes("--verbose");
const { cards, errors } = loadCards();
if (errors.length > 0) fail([...errors, "fix parse errors (run kb-validate) before drift-checking"]);
const claims = buildClaims(cards);
const declared = new Set();
for (const card of cards) {
  for (const dep of card.depends_on) declared.add(`${card.id} -> ${dep}`);
}

const extPattern = new RegExp(`(${config.extensions.map((e) => e.replace(".", "\\.")).join("|")})$`);

/** Collect analyzable files under the configured srcDirs (skip .d.ts). */
function walk(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "node_modules") walk(abs, out);
    } else if (extPattern.test(entry.name) && !entry.name.endsWith(".d.ts")) {
      out.push(abs);
    }
  }
}
const sourceFiles = [];
for (const dir of config.srcDirs) {
  const abs = path.join(REPO_ROOT, dir);
  if (fs.existsSync(abs)) walk(abs, sourceFiles);
}
sourceFiles.sort();
if (sourceFiles.length === 0) {
  fail([`no source files found under ${config.srcDirs.join(", ")} — check scripts/kb/kb.config.json`]);
}

/** Resolve an import specifier from a file to a repo-relative path, or null for bare packages. */
function resolveSpecifier(specifier, fromAbs) {
  let base = null;
  for (const [prefix, target] of Object.entries(config.aliases)) {
    if (specifier.startsWith(prefix)) {
      base = path.join(REPO_ROOT, target, specifier.slice(prefix.length));
      break;
    }
  }
  if (base === null) {
    if (specifier.startsWith(".")) base = path.resolve(path.dirname(fromAbs), specifier);
    else return null; // bare package import
  }
  const suffixes = ["", ...config.extensions, ...config.extensions.map((e) => `/index${e}`)];
  for (const suffix of suffixes) {
    const candidate = `${base}${suffix}`;
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return path.relative(REPO_ROOT, candidate);
    }
  }
  return `UNRESOLVED:${specifier}`;
}

/** Extract static import/export-from and dynamic import("...") specifiers. */
function importSpecifiers(sourceFile) {
  const specs = [];
  const visit = (node) => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      specs.push(node.moduleSpecifier.text);
    } else if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0])
    ) {
      specs.push(node.arguments[0].text);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return specs;
}

const observedEdges = new Map(); // "from -> to" => example "file imports file"
const unclaimed = new Set();
const unresolved = [];

for (const abs of sourceFiles) {
  const rel = path.relative(REPO_ROOT, abs);
  const fromCard = ownerOf(rel, claims);
  if (!fromCard) {
    unclaimed.add(rel);
    continue;
  }
  const sourceFile = ts.createSourceFile(
    rel,
    fs.readFileSync(abs, "utf8"),
    ts.ScriptTarget.Latest,
    false,
    /x$/.test(path.extname(rel)) ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  );
  for (const specifier of importSpecifiers(sourceFile)) {
    const target = resolveSpecifier(specifier, abs);
    if (target === null) continue;
    if (target.startsWith("UNRESOLVED:")) {
      if (!/\.(css|scss|svg|png|jpg|webp|json)$/.test(specifier)) unresolved.push(`${rel}: ${specifier}`);
      continue;
    }
    const toCard = ownerOf(target, claims);
    if (!toCard) {
      unclaimed.add(target);
      continue;
    }
    if (toCard === fromCard) continue;
    const key = `${fromCard} -> ${toCard}`;
    if (!observedEdges.has(key)) observedEdges.set(key, `${rel} imports ${target}`);
  }
}

const drift = [...observedEdges.keys()].filter((k) => !declared.has(k)).sort();
const unobserved = [...declared].filter((k) => !observedEdges.has(k)).sort();

if (unclaimed.size > 0) {
  console.log(`INFO   ${unclaimed.size} source file(s) owned by no card${verbose ? ":" : " (use --verbose to list)"}`);
  if (verbose) for (const f of [...unclaimed].sort()) console.log(`         ${f}`);
}
for (const u of unresolved) console.log(`INFO   unresolved import — ${u}`);
for (const edge of unobserved) {
  console.log(`INFO   declared but never imported (conceptual?): ${edge}`);
}

if (drift.length > 0) {
  for (const edge of drift) {
    console.error(`DRIFT  undeclared dependency: ${edge}   e.g. ${observedEdges.get(edge)}`);
  }
  console.error(
    `\nkb-drift: ${drift.length} undeclared edge(s). Either declare them in the cards' depends_on or remove the import.`
  );
  process.exit(1);
}
console.log(
  `kb-drift: OK — ${sourceFiles.length} files, ${observedEdges.size} card edges observed, 0 undeclared`
);
