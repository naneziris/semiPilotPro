# INSTRUCTIONS — How to use the AI development system in this repo

This repo runs two subsystems that work as one:

1. **The Knowledge Layer** — deterministic module knowledge: one card per module
   (`docs/cards/`), a closed tag vocabulary, and zero-dependency scripts
   (`scripts/kb/`) that retrieve, validate, and drift-check it.
   Full manual: `docs/README.md`.
2. **The SemiPilot pipeline** — the development process: requirements → plan →
   implementation, guarded by two critic gates, executed by specialized Copilot
   agents. Machine contract: `semipilot-core.md`.

The knowledge layer is *what the agents know*; the pipeline is *how they work*.
The pipeline's every stage retrieves through the knowledge layer — never by
grepping the codebase.

---

## The map (who/what does what)

| Piece | Kind | Job |
|---|---|---|
| `/refine-requirements` | prompt → `@refiner` | Raw idea → `requirements.md` (tags → kb-resolve → impact analysis) |
| `@spec-critic` | agent (Gate 1) | APPROVED/REJECTED verdict on the spec |
| `/create-implementation-plan` | prompt → `@planner` | Approved spec → `implementation-plan.md` |
| `/implement-plan` | prompt → `@implementer` | Plan → code + tests via the 11-step YAML rail |
| `@pattern-critic` | agent (Gate 2) | APPROVED/REJECTED verdict on the diff (incl. knowledge coverage) |
| `/fix-rejection` | prompt | Applies Gate 2's required fixes, re-runs downstream rail steps |
| `@scribe` | agent | Updates cards, manifest, ADRs, dependencies, changelog after approval |
| `/run-pipeline` | prompt | Chains all of the above autonomously; loops rejections through the fix mechanisms; pauses once for your spec approval after Gate 1; escalates when a loop can't converge |
| `/gate-triage` | prompt | Cheap structural pre-check before each critic |
| `/create-mr-description`, `/explain-changes`, `/write-tests` | prompts | Optional helpers |
| `/impact`, `/new-card`, `/sync-cards` | prompts | Knowledge-layer utilities outside the pipeline |
| `kb:validate·index·check·resolve·drift·guard·catchup` | npm scripts | The deterministic backbone (see `docs/README.md`; `kb:catchup` = solo/POC catch-up after pulls) |
| `.githooks/pre-commit` | git hook | Final backstop: blocks commits with a broken/stale knowledge layer |

Kept knowledge docs (scribe-owned): `docs/decisions.md` (ADRs),
`docs/dependencies.md` (library allowlist), `docs/CHANGELOG.md` (user-facing).

---

## The flow — what you actually do

You are handed a requirement. Here is the full cycle:

### First — after a `git pull` (solo / POC mode)

While you are the only one maintaining the knowledge layer, teammates'
merges can leave cards stale — and resolving against stale cards is the
failure mode this system exists to prevent. Before working on freshly
pulled code, run `npm run kb:catchup` (zero tokens): it lists exactly which
cards their changes touched without a card update, using a personal
baseline kept in `.git/` (never committed, invisible to the team). Fix the
flagged cards — by hand for free, or `/sync-cards` with the printed file
list — then `npm run kb:index && npm run kb:catchup -- --mark`. Nothing
flagged → just start. Once the whole team maintains cards in-PR, this step
disappears.

### Step 0 — Is the pipeline even needed?

Typo fix, rename, version bump → skip the pipeline. Edit, run the tests, commit
(the pre-commit hook still guards the knowledge layer). **Rule of thumb: if the
change needs a test, it needs the pipeline.** For a quick "what would this
touch?" without committing to a cycle, use `/impact`.

### Step 1 — Refine: `/refine-requirements` (+ your raw requirement)

What happens, in order:
1. The refiner checks `npm run kb:validate` — an unhealthy knowledge layer stops everything.
2. It proposes 1–4 tags from `docs/cards/_vocabulary.md` and **asks you to confirm** (your first touchpoint — one glance; this keeps retrieval auditable).
3. It runs `npm run kb:resolve -- --tags <confirmed>` and reads ONLY the resolved cards + relevant deep docs.
4. It may ask up to 5 clarifying questions in one message (only ones the cards can't answer).
5. It writes `.github/requirements/requirements.md` — the Impact Analysis is built from the cards' `depends_on`/`public_contracts`/`invariants`, so it is reproducible, and the `Knowledge References` section carries the tags forward. Big changes decompose into `requirements-index.md` + sub-files.

**Your job here:** confirm the tags, answer the questions. If the refiner reports "the resolved set misses module X" — that's a card gap: fix the card (or `/new-card`), don't push the pipeline through.

### Step 2 — Gate 1: `@spec-critic`

Reads the spec against the resolved cards, `docs/decisions.md` (ADRs), and
`docs/dependencies.md`. Nine checks, binary verdict. Notable: it re-runs
`kb-resolve` itself and rejects specs whose card list doesn't match; a touched
module with NO card is an automatic reject ("create the card first").

**Your job (the intent check):** the critic runs automatically — you don't
prompt it, and REJECTED loops automatically back through `/refine-requirements`
(up to 2 loops; you're pulled in only if the loop can't converge). But when it
says APPROVED, the pipeline pauses ONCE for you: read the In/Out of Scope and
acceptance criteria, confirm this is actually what you meant, and type
**approve**. The critic can verify the spec is feasible and well-formed; it
cannot verify it matches your intent — and this is the last point where a
misread idea costs one file edit instead of a full cycle. After your approval,
everything through to the scribe runs without pausing.

### Step 3 — Plan: `/create-implementation-plan`

The planner re-resolves from the spec's tags (it does NOT re-infer or read
everything), takes file paths from the cards' `code:` paths, and writes
`.github/implementation-plan.md` with: files-to-change (each with its owning
card), a test per acceptance criterion, atomic steps, dependency justification
against `docs/dependencies.md`, a **Knowledge Updates Required** section (which
cards/docs the scribe must touch), and an explicit **cross-cutting triggers**
block (every "if you change X you must also do Y" rule from copilot-instructions.md).

**Your job:** usually nothing — it flows straight to step 4 unless the planner
raises Blocking Questions.

### Step 4 — Implement: `/implement-plan`

The implementer executes the 11-step YAML rail in an isolated context: read
plan → read conventions (copilot-instructions + matching instructions files +
card invariants) → tests first (red) → code (green) → lint → typecheck → full
test suite → explain modified tests → complexity check → conventions check →
submit. Every step checkpoints to `.github/implementation-progress.json`, so a
blocked run resumes where it stopped. If the plan turns out incomplete, it
raises a `SCOPE EXPANSION REQUEST` and waits for you instead of quietly editing
extra files.

**Your job:** answer scope-expansion requests if any; otherwise wait.

### Step 5 — Gate 2: `@pattern-critic`

Eleven checks on the actual diff — plan adherence, conventions & card
invariants, dependencies, contracts (incl. the cross-cutting triggers), complexity,
tests-on-disk, rail completeness, **knowledge coverage** (`kb-guard`: every
card owning changed code must be covered by the plan's Knowledge Updates
section), dead code, lint suppression, test-change justification.

**Your job:** normally nothing. APPROVED flows straight to the scribe.
REJECTED loops automatically — `/fix-rejection` applies the required fixes,
re-runs the downstream rail steps, and resubmits to Gate 2, up to 2 loops.
You are pulled in only on **escalation** (budget exhausted, repeated identical
rejection, or a fix that hard-blocks on lint/type/tests). Complexity flags the
critic attaches surface in the final PIPELINE COMPLETE block for you to review
before committing.

### Step 6 — Document: `@scribe`

Immediately after Gate 2 approves (no pause), the scribe executes the plan's Knowledge Updates:
surgical card edits, instructions-file tweaks, ADR/dependency entries, one
changelog line — then runs `kb:validate`, regenerates `manifest.json`
(`kb:index`), and verifies coverage with `kb:guard`. It reports any gap it
noticed but was not authorized to fix.

*(Optional between 5 and 6: `/create-mr-description` — off by default, enable
via `pipeline-overrides.yaml` or by typing `mr` after the pipeline completes.)*

### Step 7 — Commit (you)

This is your real review point in autonomous mode: read the PIPELINE COMPLETE
block (Gate 2 flags, scribe gaps, rejection history in
`.github/rejection-log.md`), review the diff, then
`git add -A && git commit` — the `.githooks/pre-commit` hook re-runs
`kb:validate` + `kb:check` and prints the guard nag. If the pipeline did its
job, this passes silently. Push; CI runs the same checks plus `kb:drift`.

What rides in the one commit: the code + tests, the updated card(s), the
regenerated `docs/cards/manifest.json`, and any touched kept docs
(CHANGELOG / decisions / dependencies / instructions files). Committing
`requirements.md` and `implementation-plan.md` is recommended — reviewers
get the spec and plan next to the diff — and `.github/rejection-log.md`
commits too (audit history). `implementation-progress.json` and
`pipeline-overrides.yaml` are per-cycle scratch and are gitignored — never
commit them.

---

## Escape hatches & partial entry

- **Start mid-pipeline** (you already have a spec, or a diff): declare it in
  `.github/pipeline-overrides.yaml` (`entry_point.start_at: plan | implement |
  pattern-critic | scribe`). Starting past Gate 1 without declaring it is
  forbidden — the override file replaces "just skip the critic".
- **Override a specific critic check**: same file, `overrides:` list, one
  reason per override. Every honored override lands in
  `.github/rejection-log.md` — bypasses are recorded, never silent.
- **Force a fresh implementation run**: delete `.github/implementation-progress.json`.

## Working WITH the system (habits that keep it healthy)

- **Never bypass a card gap.** The single most important discipline: when any
  stage says "the resolved set / cards don't cover X", the answer is to fix
  cards (`/new-card`, or edit + `kb:index`), then resume. Grepping around the
  gap makes the knowledge layer confidently wrong for every future cycle.
- **Tags are closed.** New tag = a PR to `docs/cards/_vocabulary.md` with an
  owning card. Nobody — human or agent — invents tags mid-task.
- **One requirement per cycle.** Don't bundle; the decomposition policy exists
  for genuinely large changes.
- **Trust the artifacts, not memory.** Every stage reads its predecessor's
  file (`requirements.md` → `implementation-plan.md` → diff). If you edit an
  artifact by hand, downstream stages honor your edit.
- **Move the catch-up baseline only after reviewing.** `kb:catchup -- --mark`
  asserts "the cards are true as of this commit" — marking without looking
  defeats the check.
- **Ephemeral files are ephemeral.** `implementation-progress.json`,
  `pipeline-overrides.yaml` (delete after the cycle), `rejection-log.md`
  (append-only history the scribe mines at release time).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Any stage: "knowledge layer not healthy" | `npm run kb:validate`, fix what it lists (see `docs/README.md` troubleshooting) |
| Refiner asks things the cards answer | The card is stale or thin — update it, that's the bug |
| Spec-critic rejects: "missing card coverage" | `/new-card` for the module, then re-refine |
| Gate 2 rejects: "knowledge coverage" | The plan's Knowledge Updates section missed a card — planner adds it (or justifies no-change) |
| Implementer blocked mid-rail | Read the BLOCKED line; fix the underlying issue; re-run `/implement-plan` — it resumes from the failed step |
| Teammates merged code without card updates (solo/POC mode) | `npm run kb:catchup` → fix flagged cards → `kb:index` → `kb:catchup -- --mark` |
| Pre-commit hook blocks | `npm run kb:validate` / `npm run kb:index`, stage the manifest, commit again |
| Wrong/stale conventions enforced | The instructions files or card invariants are the source — fix THEM, don't override the critic |

## Reference documents

- `docs/README.md` — knowledge-layer manual (cards, scripts, workflows, CI)
- `semipilot-core.md` — pipeline contract (rail spec, schemas, policies, inventories)
- `.github/copilot-instructions.md` — repo conventions + definition of done (always in Copilot's context)
- `docs/decisions.md` / `docs/dependencies.md` / `docs/CHANGELOG.md` — the kept knowledge docs
