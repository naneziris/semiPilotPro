# Bootstrap the knowledge layer

Fill the installed templates with TRUE content, with the human approving everything that defines knowledge. Work
through the steps **in order** and **stop at every gate**. Budget: ½–2 days of the user's review time, depending
on repository size.

## Before you start

- The files must be installed. If `docs/cards/_vocabulary.md` or `scripts/kb/kb.py` is missing: with the semipilot
  CLI, run `semipilot kb init --system <system-name>` (lowercase-kebab prefix for card ids, e.g. `shop` →
  `shop.billing`). Without it, create the layout by hand from this skill's `assets/templates/` and copy
  `scripts/kb.py` to `scripts/kb/kb.py`.
- **Kill criterion:** ask who will maintain the cards. If nobody, build only Step 3 (the instructions file) and
  stop — a card system without an owner rots into deterministic misinformation.
- This is the ONE phase where broad code exploration is allowed: you are building the retrieval layer. Afterwards,
  retrieval goes through `kb resolve` only.

## Step 1 — Inventory (no gate; produces a report)

Report concisely: stack and versions; build / test / lint / typecheck commands (from manifests and CI, verified by
running them if safe); module boundaries as the code shows them; external contracts (schemas, migrations, API specs,
event formats, persisted shapes); existing docs and their apparent staleness; test layout and conventions; candidate
**seams** — modules whose changes historically break others (`git log` of reverts and fixes helps).

## Step 2 — Vocabulary → GATE

Draft `docs/cards/_vocabulary.md`: 20–50 tags in the team's language, plus synonyms. Format: one tag per line as
`` - `tag` — meaning `` (lowercase, digits, hyphens). Present the list with a one-line rationale per tag.
**STOP: the human edits and approves the vocabulary before anything else.** Your draft is a starting point; an
LLM-invented taxonomy subtly mismatches how the team thinks, and everything downstream inherits the mismatch.

## Step 3 — Instructions → GATE

Fill the main instructions file (`AGENTS.md`; template `assets/templates/AGENTS.template.md`), ≤ 80 lines:
- **Commands:** exact, verified invocations.
- **Invariants:** 8–12 rules sourced from EVIDENCE — bug-fix commits, defensive comments, README warnings, test
  names that encode a rule. Cite the evidence when presenting. No generic best practices.
- **Cross-cutting triggers:** every "change X → must also do Y" pair you found.
- The **knowledge router** block (`assets/templates/AGENTS-router-block.md`) at the end.

Then draft 3–6 path-scoped area files `.github/instructions/<area>.instructions.md` (template
`area.instructions.template.md`), ≤ 40 lines each. GitHub Copilot loads them automatically by `applyTo`; other
agents are told by the router to read the ones matching the files they touch.
If the repository uses `CLAUDE.md` as well, make it a one-line `@AGENTS.md` import so there is one source of truth.
**STOP: the human approves the instructions and area files.**

## Step 4 — Cards, seam-first, in batches → GATE per batch

1. Propose the card LIST first (one line each: slug, owned tags, code paths). Every vocabulary tag gets exactly one
   owning card; every major source directory is claimed by some card. **STOP: the human approves the list.**
2. Write cards in batches of ~5, seam-first (modules touching external contracts or with cross-module bug history
   first), following [card-format.md](card-format.md). For each card verify every `code:` path exists and every
   fact against the code; mark inferences `(unverified)`. Run `kb validate` after each batch and fix what it reports.
   **STOP after each batch: the human reviews. An unreviewed card is a liability, not knowledge.**
   Large repository: delegate one domain per pass with [cartographer.md](cartographer.md) and consolidate.

## Step 5 — Wire the graph and go green

1. `kb index` — the manifest, ready to commit.
2. `kb drift` — for every DRIFT edge: declare it in the card (usual) or flag a genuinely surprising import to the
   human. Re-run until 0 undeclared. Set `srcDirs` / `aliases` / `extensions` in `scripts/kb/kb.config.json` first
   if the source layout is not `src/` (monorepo: list the package roots and map workspace aliases like
   `"@acme/": "packages/"`).
3. `kb resolve --tags <two common tags>` — sanity-check that the resolved sets look right to a human.
4. Seed `docs/decisions.md` with the 3–8 decisions that already shape the repository (from inventory evidence) and
   `docs/dependencies.md` from the manifests plus any bans you can evidence; unknown policy lines stay TODO.
   Remove the remaining `{{TODO}}` markers, or list the ones you could not fill.

## Step 6 — Handover report

Files created and filled; `kb validate` / `kb index --check` / `kb drift` output lines; TODOs left for the human;
reminders: activate the hook once per clone (`git config core.hooksPath .githooks`), review the CI workflow (drift
is warning-only by design), and the smoke test — ask an agent in a fresh chat a question one of the invariants
answers; it should answer cold. Then `kb catchup --mark` to set the freshness baseline.
