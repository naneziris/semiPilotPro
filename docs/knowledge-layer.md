# The knowledge layer

An optional, deterministic map of your codebase that agents read instead of searching: one **card** per module, a
**closed vocabulary** of tags, and `scripts/kb/kb.py`, which turns tags into an exact reading list and keeps the map
honest. Same tags in, same files out — for every agent, every run, every reviewer.

## Principles

1. **Determinism over semantics.** Retrieval is a walk over explicit, reviewed metadata, never semantic search.
2. **Progressive disclosure.** A tiny always-loaded router (`AGENTS.md`) → tags → cards → deep docs → code, each rung
   loaded only when the one above says so. Context cost scales with the task, not the codebase.
3. **Generated files are validated, not committed** — except one small reviewable index (`manifest.json`).
4. **Staleness is the #1 failure mode.** Stale metadata loads the wrong files with full confidence. Freshness is
   enforced by a hook and CI, not hoped for.
5. **Humans own the vocabulary and approve every card.** Agents draft; people decide what is true.

## The pieces

| Piece | Where |
|---|---|
| Closed vocabulary — 20–50 tags, one owning card each | `docs/cards/_vocabulary.md` |
| Module cards — frontmatter + 3–8 sentence summary, ≤ 80 lines | `docs/cards/<module>.md` |
| Manifest — generated, committed | `docs/cards/manifest.json` |
| Deep docs | `docs/deep/*.md` |
| Router + invariants | `AGENTS.md` (ends with the knowledge router block) |
| Area rules | `.github/instructions/*.instructions.md` (`applyTo` globs) |
| ADRs, dependency policy, changelog | `docs/decisions.md`, `docs/dependencies.md`, `docs/CHANGELOG.md` |
| The tool | `scripts/kb/kb.py` — Python 3.9+, standard library and git only |
| Enforcement | `.githooks/pre-commit`, `.github/workflows/knowledge-layer.yml` |

A card:

```markdown
---
id: shop.orders
owns: [orders, order-search]
depends_on: [shop.db, shop.auth]
public_contracts:
  - "listOrders(filters, page) -> OrderPage  (src/orders/service.ts)"
code:
  - src/orders/
docs:
  - docs/deep/order-status-machine.md
invariants:
  - "Every order query goes through listOrders(); never query the orders table directly"
---
Orders owns the order lifecycle … (3–8 sentences)
```

Every tag and every code path has exactly one owning card (for nested paths the longest claim wins), so "whose file
is this?" never has two answers. Full schema and every validation error:
[skills/semipilot-knowledge/references/card-format.md](../skills/semipilot-knowledge/references/card-format.md).

## The tool

```bash
python3 scripts/kb/kb.py validate                 # cards well-formed, paths exist, edges resolve   (exit 1 on error)
python3 scripts/kb/kb.py index [--check]          # write the manifest; --check fails when it is stale
python3 scripts/kb/kb.py resolve --tags a,b [--json]   # tags → cards (L1), deep docs (L2), code paths (L3)
python3 scripts/kb/kb.py drift [--verbose]        # real imports vs declared depends_on      (exit 1 on drift)
python3 scripts/kb/kb.py guard [--files …]        # card-owned code changed without its card (never fails)
python3 scripts/kb/kb.py catchup [--mark]         # cards made stale since your personal baseline
```

`semipilot kb <command>` runs the same tool from anywhere in the project. `resolve` walks one hop along
`depends_on` **and** along reverse dependents, so a change to a shared module brings in its consumers.

`drift` reads the real import graph: TypeScript/JavaScript (`import … from`, `export … from`, `import()`,
`require()`, with path aliases) and Python (`import`, `from … import`, relative imports). Configure the layout in
`scripts/kb/kb.config.json`:

```json
{ "srcDirs": ["src"], "aliases": { "@/": "src/" }, "extensions": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".py"] }
```

Monorepo: list the package roots in `srcDirs` and map workspace aliases (`"@acme/": "packages/"`). The JS extractor
is a deliberately simple pattern match (no compiler needed): comments and template literals are ignored, but an
import-looking sequence inside an ordinary string literal can still show up as DRIFT, and packages resolved only
through `package.json` `exports` are not followed.

## Install

```bash
semipilot kb init --system shop           # card ids become shop.<module>
git config core.hooksPath .githooks       # once per clone, every teammate — the exact path kb init prints
```

`kb init` copies `kb.py`, its config, the hook, the CI workflow and the templates (vocabulary, card and area
templates, `docs/README.md`, ADRs, dependencies, changelog), and appends the knowledge router to `AGENTS.md`. It never
overwrites knowledge content. In a monorepo subfolder, the CI workflow goes to the repository root as
`knowledge-layer-<project-path>.yml` with `working-directory` set to the project (one workflow per project), and the
hook path is printed for you. If `core.hooksPath` already points at another hook manager (husky, pre-commit), `kb init`
says so instead of telling you to replace it — call `.githooks/pre-commit` from your existing hook.

The loop's own commits skip hooks (`--no-verify`), so a task that renames a card-owned file cannot crash a run; the
scribe updates the card afterwards and your next commit, and CI, check it.

Then fill it: `/semipilot-knowledge bootstrap` in your agent's chat. Inventory → vocabulary (gate) → instructions
(gate) → card list (gate) → cards in batches of ~5 (gate each) → `drift` to green → handover. Budget ½–2 days of
review. The kill criterion comes first: if nobody will maintain the cards, stop after the instructions file.

## Day to day

| When | Do | Cost |
|---|---|---|
| Starting a change | `/semipilot-knowledge impact <change>` — tags → resolve → impact brief | small |
| Building with semiPilot | nothing — the refiner records the tags, the loop resolves them for every agent | — |
| After a semiPilot feature | `/semipilot-scribe <feature>` — applies the plan's *Knowledge Updates Required* | small |
| After any other change | `/semipilot-knowledge sync` | small |
| A new module | `/semipilot-knowledge new-card <module>` | small |
| After pulling teammates' work | `kb catchup`, fix flagged cards, `kb catchup --mark` | zero to detect |
| Every commit | the hook: `validate`, `index --check`, `guard` | zero |
| Every PR | CI: `validate` + manifest (blocking), `drift` (warning), `guard` (summary) | zero |

Retrieval, validation, freshness and enforcement are scripts and cost nothing; tokens are spent once to build the
knowledge and a little per change to keep it true.

## With the loop

When `docs/cards/_vocabulary.md` and `scripts/kb/kb.py` exist (`knowledge_layer.mode: auto`):

- preflight runs `kb validate` and resolves the requirements' tags — an unhealthy layer or an unknown tag stops the
  run before anything is spent;
- every agent call carries the resolved reading list, and the instruction to honor card invariants and contracts;
- the planner emits `knowledge_updates`, rendered as *Knowledge Updates Required* in `implementation-plan.md`;
- the loop never writes to cards, instructions, ADRs or the changelog.

Force it with `knowledge_layer: {mode: on | off}`.

## Coming from the Node scripts

Layers installed before v0.2 used `scripts/kb/kb-*.mjs`. They keep working: semiPilot detects them and calls
`node`. To switch, run `semipilot kb init --force` — it adds `kb.py` and rewrites only the hook and the CI workflow;
cards, vocabulary and docs are untouched, and the existing `manifest.json` is accepted as-is. Then delete the
`.mjs` files and the `kb:*` scripts in `package.json`. See [upgrading.md](upgrading.md).
