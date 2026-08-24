---
description: "Bootstrap the knowledge layer in this repo: inventory → vocabulary → instructions → cards (seam-first) → green kb suite. Human approval gates at every knowledge-defining step."
---

You are bootstrapping this repository's knowledge layer. The kit's files are
installed (scripts/kb/, templates with `{{TODO}}` markers, prompts); your job
is to fill them with TRUE content, with the human approving everything that
defines knowledge. Work through the steps IN ORDER and STOP at every gate.

Ground rules for the whole bootstrap:
- You are drafting; the human owns the truth. Never advance past a gate
  without explicit approval.
- Everything you write must be verifiable in the repo. No aspirational
  content, no invented conventions, no guessed invariants.
- This is the ONE phase where broad code exploration is allowed — you are
  BUILDING the retrieval layer, so you may read the codebase freely. After
  bootstrap, retrieval goes through `kb-resolve` only.

## Step 1 — Inventory (no gate, produces a report)

Explore the repo and report, concisely:
- Stack, build/test/lint/typecheck commands (from manifests and CI, verified
  by running them if safe).
- Module boundaries as the CODE shows them (top-level dirs, package layout).
- External contracts: DB schemas/migrations, API specs, event formats,
  persisted-storage shapes.
- Existing docs and their apparent staleness.
- Test layout and conventions.
- Candidate "seams": modules whose changes historically break others
  (git log of reverts/fixes helps).

## Step 2 — Vocabulary draft → GATE

Fill `docs/cards/_vocabulary.md`: 20–50 tags in the team's language, from the
inventory, plus synonyms. Present the list with a one-line rationale per tag.
**STOP: the human edits/approves the vocabulary before anything else.** The
vocabulary is human-owned; your draft is a starting point, not an answer.

## Step 3 — Instruction router draft → GATE

Fill the `{{TODO}}` blocks in `.github/copilot-instructions.md`:
- Commands: exact, verified invocations.
- Invariants: 8–12 rules sourced from EVIDENCE — bug-fix commits, defensive
  comments, README warnings, test names that encode a rule. Cite the evidence
  when presenting. Do not pad with generic best practices.
- Cross-cutting triggers: every "change X → must also do Y" pair you found.
Keep the file ≤ 80 lines. Then draft 3–6 path-scoped
`.github/instructions/<area>.instructions.md` files (template:
`docs/cards/_templates/area.instructions.template.md`), each ≤ 40 lines.
If `AGENTS.md` needed the router block appended (installer note), do it.
**STOP: human approves the router + area files.**

## Step 4 — Cards, seam-first, in batches → GATE per batch

Using `docs/cards/_templates/card.template.md` (id prefix `{{SYSTEM}}.`):
1. Propose the card LIST first (one line each: slug, owned tags, code paths).
   Every vocabulary tag must get exactly one owning card; every major source
   dir should be claimed by some card. **STOP: human approves the list.**
2. Author cards in batches of ~5, seam-first (modules touching external
   contracts or with cross-module bug history first). For each card: verify
   every `code:` path exists, every fact against the code, keep ≤ 80 lines.
   Run `npm run kb:validate` after each batch and fix what it reports.
   **STOP after each batch: human reviews — an unreviewed card is a
   liability, not knowledge.**
   (For large repos, batches can be delegated to `@cartographer` — one
   domain per invocation; you consolidate and validate.)

## Step 5 — Wire the graph and go green

1. `npm run kb:index` — commit-ready manifest.
2. `npm run kb:drift` — for every DRIFT edge: declare it in the card (usual)
   or flag a genuinely surprising import to the human. Re-run until 0
   undeclared. (Non-TS repo: skip and tell the human to disable the drift CI
   job.)
3. `npm run kb:resolve -- --tags <two common tags>` — sanity-check the
   resolved sets look right to a human.
4. Fill `docs/decisions.md` (seed ADRs for the 3–8 decisions that already
   shape the repo — from the inventory evidence), `docs/dependencies.md`
   (from the manifest + any bans you can EVIDENCE; unknown policy lines stay
   TODO for the human), and delete remaining `{{TODO}}` markers everywhere
   or list the ones you could not fill.

## Step 6 — Handover report

Report: files created/filled; kb suite status (validate/check/drift output
lines); TODOs left for the human; reminder list — `git config core.hooksPath
.githooks`, review the CI workflow (drift job is warning-only by design),
and the smoke test: ask Copilot in a fresh chat a question one of the
invariants answers — it should answer cold. If the pipeline layer is
installed, point the human at `INSTRUCTIONS.md` for the first real cycle.
