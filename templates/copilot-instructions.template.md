# {{REPO_NAME}} — AI instructions

<!-- TEMPLATE NOTES (delete this comment when filled):
     Keep the whole file ≤ 80 lines. It loads on EVERY Copilot request — it is
     an L0 router, not an encyclopedia. Depth belongs in cards and instructions
     files. The bootstrap prompt fills the {{TODO}} blocks from the repo. -->

{{TODO: 2–4 sentences — what the product/service is, the stack, the deployment target.}}

## Commands

- {{TODO: dev / build / test / typecheck / lint commands, one line each — exact invocations.}}
- Knowledge layer: `npm run kb:validate` · `npm run kb:resolve -- --tags <t1,t2>` · `npm run kb:drift`

## How to find module knowledge (do this before planning any change)

Module knowledge lives in `docs/cards/` — one card per module, YAML
frontmatter + summary. Do NOT grep the whole codebase to build context.
Instead: pick tags from `docs/cards/_vocabulary.md` (closed list), run
`npm run kb:resolve -- --tags <tags>`, and read only the files it returns.
Cards point to deep docs (`docs/deep/`) and code paths; follow those
pointers. If the resolved set looks wrong, fix the cards — don't bypass them.

## Non-negotiable invariants

{{TODO: the 8–12 rules that have each caused or prevented a real bug in THIS
repo. Numbered. Concrete ("bump X when Y changes"), never aspirational
("write clean code"). Source them from bug history, not imagination.}}

## Cross-cutting triggers

<!-- The pipeline's planner and critics reference this section by name.
     List every "if you change X, you must also do Y" pair in the repo. -->

{{TODO: e.g. "persisted-schema change → version bump + migration",
"public asset change → cache-buster bump", "API change → client/mock update".
If none are known yet, write "None identified yet — add them as they bite."}}

## The pipeline (for behavioral changes)

Non-trivial changes go through the SemiPilot pipeline: `/refine-requirements`
→ `@spec-critic` (Gate 1) → `/create-implementation-plan` → `/implement-plan`
→ `@pattern-critic` (Gate 2) → `@scribe` — or `/run-pipeline` to chain them.
Contract: `semipilot-core.md`. Human manual: `INSTRUCTIONS.md`. Rule of thumb:
if the change needs a test, it needs the pipeline; trivial edits skip it.

## Change discipline

Keep diffs surgical. When your change touches files under a card's `code:`
paths, update that card in the same PR (CI nags otherwise). New modules get
a new card (`.github/prompts/new-card.prompt.md` scaffolds one).
{{TODO: one or two repo-specific discipline lines — where tests live, what
"done" means here beyond the kb checks.}}
