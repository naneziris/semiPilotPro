# AI-Ready Repository Playbook

**How to build a knowledge layer and make any repository ready for agentic tooling (GitHub Copilot in VS Code, and portable to Claude Code, Cursor, and CLI agents).**

The design rationale behind this kit. Follow it top to bottom for each new repository; steps marked **[multi-repo]** apply only when the repo is one of several connected applications. (`INSTALL.md` is the operational version of the same steps — this document carries the why.)

---

## Principles (read once, they drive every step)

1. **Determinism over semantics.** Retrieval is graph traversal over explicit, hand-reviewed metadata — never semantic search. Scripts return the same file set for the same input, every time. Embeddings are at most a fallback discovery aid, never the authority.
2. **Progressive disclosure.** Every artifact carries pointers, not payloads. An agent starts from a tiny always-loaded index and descends only along the branches the task needs. Context cost scales with the *task*, not the *codebase*.
3. **Generated files are validated, not committed.** Anything a tool can regenerate (AST graphs, dependency dumps) is produced fresh, compared against hand-written metadata, and discarded. Committing generated artifacts creates merge churn and then demands infrastructure (artifact stores, overlays) to fix a self-inflicted problem. The one exception: a tiny, human-reviewable index (`manifest.json`) derived from the hand-written cards.
4. **Staleness is the #1 failure mode.** Stale metadata is worse than none — it deterministically loads the *wrong* files with full confidence. Freshness enforcement (CI guards) is the load-bearing component; budget effort accordingly.
5. **Humans own the vocabulary and review every card.** LLMs draft; humans approve. An unreviewed card is a liability, not knowledge.

---

## The artifact inventory (what "AI ready" means, concretely)

| Layer | Artifact | Location | Loaded when |
|---|---|---|---|
| L0 | Repo instruction router | `.github/copilot-instructions.md` (+ `AGENTS.md` for other agents) | Always, automatically |
| L0 | Path-scoped rules | `.github/instructions/*.instructions.md` with `applyTo` globs | When matching files are in play |
| L1 | Module cards | `docs/cards/*.md` | After tag resolution via `kb-resolve` |
| L1 | Closed vocabulary | `docs/cards/_vocabulary.md` | Referenced by prompts/scripts |
| L1 | Generated index | `docs/cards/manifest.json` | Script input; tiny, committed |
| L2 | Deep docs | `docs/deep/*.md` | Only when a card's `docs:` entry is relevant |
| L3 | Source code | the repo | Execution time only, guided by card `code:` paths |
| Tooling | Script suite | `scripts/kb/` (validate, index, resolve, drift) | By agents and CI |
| Workflow | Prompt files | `.github/prompts/*.prompt.md` | On slash-command invocation |
| Workflow | Custom agent | `.github/agents/*.agent.md` | When selected in chat |
| Guard | CI workflow | `.github/workflows/knowledge-layer.yml` | Every PR |
| **[multi-repo]** | Contract registry | small dedicated repo, one md per seam | Cross-repo impact analysis |

---

## Step-by-step

### Step 0 — Inventory (½ day)

Answer in writing before creating anything: What are the module boundaries as the *team* names them? Which invariants have caused real bugs twice or more? What are the external contracts (DB schema, API specs, feed formats, storage schemas)? Which docs exist and which are stale? Who will maintain the layer?

Kill criterion: if nobody will own maintenance, build **only Step 2** (the instruction router) and stop — a full card system without an owner rots into deterministic misinformation (Principle 4).

### Step 1 — Hand-write the closed vocabulary (½ day)

`docs/cards/_vocabulary.md`: 20–50 capability tags matching the team's real language, plus a synonyms/glossary section. Closed: new tags enter only by PR. Do **not** let an LLM invent the taxonomy — every downstream classification inherits its subtle mismatches.

### Step 2 — The instruction router (1 day; do this even if you do nothing else)

1. `.github/copilot-instructions.md`, ≤ 80 lines: stack summary; build/test/run commands; the 8–12 invariants that repeatedly bite; a router paragraph pointing to `docs/cards/` and `kb-resolve`. It is an L0 artifact — a 500-line instruction file loaded on every request is an L0 artifact doing L2's job.
2. `.github/instructions/<area>.instructions.md` per major area, each ≤ 40 lines, with YAML frontmatter `applyTo: "<glob>"`. Area-local invariants + a pointer to the area's card. This is what keeps the global file thin.
3. `AGENTS.md` at repo root with the same content or a pointer to the Copilot file — it makes the router portable to Copilot coding agent, Claude Code, Cursor, and CLI agents. In VS Code, enable `chat.useAgentsMdFile`. If the repo already has agent files, align them; never maintain two divergent routers.
4. Commit shared workspace settings (`.vscode/settings.json`) for any non-default `chat.*` locations.

**Verify:** ask Copilot chat a question whose answer is one of the invariants; it must answer correctly with an empty chat context.

### Step 3 — Module cards (2–4 days depending on repo size)

One Markdown file per module in `docs/cards/`, YAML frontmatter + prose body, ≤ 80 lines:

```yaml
---
id: <repo>.<module>            # globally unique
owns: [tag1, tag2]             # from the closed vocabulary ONLY
depends_on: [<repo>.<other>]   # card ids
public_contracts:              # things whose change can break someone else
  - "POST /invoices (v2)"
code: [src/billing/, src/lib/tax.ts]
docs: [docs/deep/billing.md]
invariants:
  - Finalized invoices are immutable; corrections via credit notes
---
Three to eight sentences of prose: what the module does, its boundaries,
and its non-obvious behaviors. A summary, not a spec — depth lives in docs:.
```

Rules: one card per module; a fact about X lives only in X's card; if a card exceeds ~80 lines, split the module or push detail to `docs/deep/`; hierarchical cards (system → domain → module) only at large scale. Author **seam-first**: start with modules that touch external contracts or have a cross-module bug history, grow inward. LLM drafts, human reviews, every card.

### Step 4 — The deterministic script suite (1–2 days first time; then copy it)

Four scripts in `scripts/kb/`, any language, only dependency a YAML-frontmatter parser. **Write them once, then carry the folder from repo to repo** — only the depcruise config and glob conventions change.

| Script | Specification |
|---|---|
| `kb-validate` | Parse all cards. Fail on: frontmatter schema violations; `code:` paths that don't exist; `depends_on` ids that don't resolve; tags outside `_vocabulary.md`. |
| `kb-index` | Cards → `manifest.json` (tag → card ids, plus the edge list). Deterministic output (sorted keys). `--check` mode: regenerate and fail if it differs from the committed file. |
| `kb-resolve --tags t1,t2` | Fixed traversal: cards matching the tags → one hop along `depends_on` and reverse edges → append linked `docs:`. Prints the exact file list. The agent's ONLY sanctioned retrieval mechanism. |
| `kb-drift` | Compute the real dependency graph fresh (dependency-cruiser for JS/TS; import parsers or tree-sitter for other stacks), fold file edges up to card level via `code:` globs, diff against declared `depends_on`. Report undeclared and phantom edges. Output discarded, never committed. |

This satisfies "as much scripting as possible for deterministic, higher-quality output" without committing a single generated artifact.

### Step 5 — CI guards (½ day)

`knowledge-layer.yml` on every PR:

1. `kb-validate` + `kb-index --check` → **blocking** from day one.
2. `kb-drift` → warning first, blocking once the noise floor is known.
3. `kb-guard` diff rule: PR touches files under a card's `code:` paths without touching any card → PR comment nag (small team) or merge block (larger team / after the habit sticks). This is the staleness defense — the single highest-leverage piece of the whole system.

### Step 6 — Workflow artifacts for the agent (1 day)

1. `.github/prompts/impact.prompt.md` — the pipeline with its two human gates: requirement → tags proposed *from the closed vocabulary only* → **human confirms** (gate 1) → run `kb-resolve` → read only the returned files → impact brief with open questions → **human answers** (gate 2) → plan. Tag mapping is the one non-deterministic step; make it auditable rather than pretending it away.
2. `.github/prompts/new-card.prompt.md` — scaffold a card that passes `kb-validate`.
3. `.github/prompts/sync-cards.prompt.md` — post-change: list stale cards/instructions, draft diffs.
4. `.github/agents/planner.agent.md` — a custom agent whose instructions forbid reading outside the resolved set. If the resolved set is wrong, fix the cards, don't bypass them.
5. MCP servers (`.vscode/mcp.json`) only when a workflow concretely needs one (e.g. GitHub issues/PRs). A CLI script the agent can run is simpler and more deterministic than a custom MCP tool; don't build servers for retrieval the scripts already do.

### Step 7 — [multi-repo] Contract registry (1 day + ongoing)

Only when this repo is one of several connected applications. Changes propagate between apps through **contracts** (APIs, events, shared schemas, embedded widgets, auth handoffs), not through repos — so cross-repo edges live at contract level, in one small dedicated registry repo: one md per seam (frontmatter: id, kind, version, producer, consumers, schema pointer), plus the shared vocabulary and the CI-generated cross-repo `manifest.json`/`graph.json`. Card `public_contracts:` entries reference registry ids. `kb-resolve` then adds: if a touched card produces a contract, pull in **all** consumer cards across repos. The litmus test for "is this a contract": if changing it could require a change in another repo, it is.

### Step 8 — Maintenance loop (ongoing)

Card updates ride in the same PR as the code change. `kb-drift` catches what habit misses. Periodically: split oversized cards, prune dead tags, distill stabilized session notes into cards/deep docs. When onboarding a new repo, copy `scripts/kb/`, write vocabulary + router first, cards seam-first after.

---

## What NOT to build

No MCP server for knowledge retrieval. No vector database. No graph database. No committed AST/code graphs. No remote artifact store + overlay pipeline. No orchestration framework. Markdown + YAML frontmatter + four small scripts is the entire tool. If you outgrow it you will know exactly what to build then — and you'll have the metadata to migrate.

## Pitfalls checklist

- ☐ Vocabulary hand-written, closed, changed only by PR
- ☐ Instruction router ≤ 80 lines; area rules path-scoped via `applyTo`
- ☐ One router of truth — `AGENTS.md` and `copilot-instructions.md` never diverge
- ☐ Every AI-drafted card human-reviewed before commit
- ☐ Cards ≤ 80 lines; detail pushed to `docs/deep/`
- ☐ Generated graphs validated-and-discarded, never committed (manifest.json excepted)
- ☐ `kb-guard` staleness nag active in every repo — this is the load-bearing guard
- ☐ Agents forbidden from reading outside the resolved set; fix cards, don't bypass
- ☐ Both human gates kept in the impact pipeline
- ☐ No owner → build Step 2 only

## Per-repo quick checklist (copy per repository)

1. ☐ Step 0 inventory written, owner named
2. ☐ `_vocabulary.md`
3. ☐ `copilot-instructions.md` + `*.instructions.md` + `AGENTS.md` aligned
4. ☐ Seam-first cards reviewed and merged
5. ☐ `scripts/kb/` copied in, depcruise/glob config adapted, all four scripts green
6. ☐ CI workflow live (validate blocking, drift warning, guard nag)
7. ☐ Prompt files + planner agent
8. ☐ [multi-repo] contracts registered; `public_contracts` wired
