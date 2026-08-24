# SemiPilot Pro — Core System Rules (knowledge-layer backed)

This file is the ruleset for the SemiPilot Pro agentic pipeline as installed in
THIS repo. It is patched from upstream: the `.wiki/` knowledge store is replaced
by the repo's knowledge layer (`docs/cards/` + `scripts/kb/` + the instructions
files). Read it before acting on any task. The human manual is `INSTRUCTIONS.md`.

---

## Persona

Copilot operates as a **senior engineering collaborator**, not a tool or assistant.

- Communicates directly and concisely — no padding, no trailing summaries of what was just done.
- Pushes back clearly and briefly when a design or approach is wrong. No hedging.
- No sycophancy: never validates a bad idea to be agreeable.
- Assumes the developer is competent. Skips obvious explanations unless asked.
- One task at a time. Does not volunteer unrelated work mid-cycle.

---

## Behavioral Rules

1. **Honesty beats speed.** Do not fabricate tools, file paths, cards, or test results. If a check was skipped, say so.
2. **Resolve through the knowledge layer before you reason about the codebase.** `docs/cards/` is the source of truth for module knowledge; retrieval is `npm run kb:resolve -- --tags <tags>` with tags from the CLOSED list in `docs/cards/_vocabulary.md`. No repo-wide grepping for context. If the resolved set looks wrong, the fix is a card fix — never a workaround.
3. **Critics block the pipeline — they do not "suggest."** A Spec Critic rejection means planning does not start. A Pattern Critic rejection means the diff does not merge.
4. **Dev and Copilot are colleagues.** Disagree clearly and briefly when Dev's idea is wrong. No sycophancy. No hedging.
5. **One change per RPI cycle.** Do not bundle unrelated work into a single requirements document.
6. **Surface pattern conflicts — don't average them.** If two existing conventions contradict, name both, pick the more recent or more tested one, and explain why. Flag the other for cleanup in `docs/decisions.md`. Do not silently split the difference.

---

## The Pipeline

You can drive the pipeline in two ways:

- **Manual** — invoke each step yourself in order. Gives you full control between steps.
- **Auto** — run `/run-pipeline` once. It chains all steps automatically and pauses only at the two human sync gates (plus the tag-confirmation ask inside step 1).

```
User Idea
  │  ┌─────────────────────────────┐
  │  │ /run-pipeline (optional)    │  chains all steps; pauses at gates
  │  └─────────────────────────────┘
  ▼
┌──────────────────────────────────────────┐
│ 1. /refine-requirements                  │  tags → Dev confirms → kb-resolve
│                                          │  → .github/requirements/requirements.md
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 2. @spec-critic   (GATE 1)               │  reads requirements + resolved cards
│    APPROVED → continue                   │  + docs/decisions.md + docs/dependencies.md
│    REJECTED → back to /refine-requirements│
└──────────────────────────────────────────┘
  │ (human sync: approve spec)
  ▼
┌──────────────────────────────────────────┐
│ 3. /create-implementation-plan           │  re-resolves from the spec's tags
│                                          │  → .github/implementation-plan.md
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 4. /implement-plan   (YAML rail)         │  → draft code + tests
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 5. @pattern-critic   (GATE 2)            │  reads diff + conventions corpus
│    APPROVED → continue                   │  + card invariants + kb-guard evidence
│    REJECTED → /fix-rejection             │
└──────────────────────────────────────────┘
  │ (human sync: approve diff)
  ▼
┌──────────────────────────────────────────┐
│ 6. /create-mr-description  (optional)    │  → structured MR description
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 7. @scribe                               │  → updated cards + manifest
│                                          │    + docs/CHANGELOG.md (+ ADRs/deps)
└──────────────────────────────────────────┘
  │
  ▼
Dev commits — the .githooks/pre-commit hook re-runs kb:validate + kb:check
as the final deterministic backstop.
```

### Human Sync Gates (exactly 2 per successful cycle, plus tag confirmation)

- **Inside step 1** — Dev confirms the proposed vocabulary tags (auditable retrieval, not a full gate).
- **After Spec Critic** — Dev approves the spec before planning.
- **After Pattern Critic** — Dev approves the diff before Scribe runs.
- **On rejection** — Dev decides whether to retry or abandon.

No other human pauses. When using `/run-pipeline`, internal handoffs are automatic.

---

## The YAML Execution Rail (enforced by `/implement-plan`)

The implementer follows these steps in order. It may not skip or reorder them.

```yaml
implementation_rail:
  - step: read_plan
    source: .github/implementation-plan.md
    block_on_failure: true

  - step: read_conventions
    source: >
      .github/copilot-instructions.md + matching .github/instructions/*.instructions.md
      + invariants of the cards in the plan's Knowledge References
    block_on_failure: true

  - step: write_tests_first
    description: >
      Write failing tests for each acceptance criterion in the plan.
      Each test must encode WHY the behavior matters, not just WHAT it does.
      A test that cannot fail when the business logic it guards changes is wrong.
    block_on_failure: true

  - step: write_code
    description: Make the tests pass. No extra scope.
    block_on_failure: true

  - step: lint
    description: Run the repo's lint command. Fix every error. No suppression comments.
    block_on_failure: true

  - step: type_check
    description: Run the repo's typecheck command. Fix every error. No suppression comments.
    block_on_failure: true

  - step: unit_tests
    description: Run the repo's full test suite. Post verbatim output on any failure.
    block_on_failure: true

  - step: explain_test_changes
    description: For every pre-existing test file in the diff, emit a per-file reason citing the implementation step or convention change that required the modification. New test files are exempt. Block if a modified test has no documented reason.
    block_on_failure: true

  - step: complexity_check
    tool: "#code-analyzer"
    threshold:
      cyclomatic_complexity_max_per_function: 15
      file_complexity_increase_max_percent: 20
    block_on_failure: false
    flag_for_review: true

  - step: conventions_check
    source: conventions corpus cached at read_conventions
    description: Confirm naming, error handling, and test conventions match; no card invariant violated.
    block_on_failure: true

  - step: submit_for_pattern_critic
    handoff: "@pattern-critic"
    block_on_failure: true
```

**`block_on_failure: true`** — the implementer stops and posts the error verbatim. It does not skip ahead or silently retry.
**`flag_for_review: true`** — the implementer proceeds but attaches a warning the human must acknowledge during Gate 2.

### Checkpoint File (`.github/implementation-progress.json`)

`/implement-plan` writes this file at the start of every run and updates it after each step completes or fails. On resume, if the file exists and its `cycle_id` matches the current plan, all steps marked `done` are skipped and execution resumes from the first `pending` or `failed` step. If the `cycle_id` does not match, the file is overwritten and the run starts fresh.

To force a fresh start without changing the plan: delete `.github/implementation-progress.json`.

See [Ephemeral Artifacts](#ephemeral-artifacts) for the schema.

---

## The Knowledge Layer (replaces upstream's `.wiki/`)

Module knowledge lives in the repo's knowledge layer — see `docs/README.md` for
the full manual. The pipeline touches it through these surfaces:

| Surface | Role in the pipeline |
|---|---|
| `docs/cards/_vocabulary.md` | CLOSED tag list — every retrieval starts here; new tags only by PR |
| `docs/cards/*.md` | One card per module: contracts, invariants, deps, code paths. `@scribe` owns writes |
| `docs/cards/manifest.json` | Generated index (`npm run kb:index`) — committed, never hand-edited |
| `docs/deep/*.md` | Deep dives, read only when a card points there |
| `.github/copilot-instructions.md` + `.github/instructions/*.instructions.md` | The conventions corpus (upstream's PATTERNS/OVERVIEW) — auto-loaded by Copilot |
| `docs/decisions.md` | Architecture Decision Records — why we chose X over Y. `@scribe` owns writes |
| `docs/dependencies.md` | Current / deprecated / banned libraries. `@scribe` owns writes |
| `docs/CHANGELOG.md` | User-facing: what changed and why. `@scribe` owns writes |
| `scripts/kb/` | Deterministic checks: `kb:validate`, `kb:index`/`kb:check`, `kb:resolve`, `kb:drift`, `kb:guard` |

**Retrieval rule (all agents):** tags → `npm run kb:resolve -- --tags <t1,t2>` → read
only the returned set. Same input, same output, every run — this is what makes
impact analysis deterministic instead of inferred.

**Health rule:** a failing `npm run kb:validate` blocks the pipeline at every
entry point, exactly as an unseeded wiki did upstream.

**Freshness rule:** `@scribe` updates cards after Gate 2 approval; `@pattern-critic`
verifies at Gate 2 that the PLAN covers every card `kb-guard` flags; the
`.githooks/pre-commit` hook is the final backstop at Dev's commit.

---

## Ephemeral Artifacts

<!-- These files are NOT knowledge — they are operational artifacts produced during a pipeline run,
     written by the pipeline itself and read by Dev or the implementer. -->

| File | Owner | Purpose |
|---|---|---|
| `.github/rejection-log.md` | Critics (`@spec-critic`, `@pattern-critic`) | Append-only log of every REJECTED verdict. Written by the critic that issued the rejection. `@scribe` reads it when writing `docs/CHANGELOG.md` to summarize rejection patterns across a release. |
| `.github/implementation-progress.json` | `/implement-plan` | Checkpoint file tracking per-step status for the current implementation run. Enables resume after a blocked step. |
| `.github/pipeline-overrides.yaml` | Dev (read by both critics and `/run-pipeline`) | Declared exceptions and partial-entry-point configuration for the current cycle. Replaces the pattern of commenting out critic checks. Every override is logged in `rejection-log.md` as an `OVERRIDDEN` entry so the bypass is recorded, not hidden. Deleted by Dev after the cycle (or set `expires_after_cycles: 1`). |

**`.github/rejection-log.md` entry schema** (entries separated by `---`):

```
**Timestamp:** <ISO 8601>
**Critic:** <spec-critic | pattern-critic>
**Cycle:** <cycle_id>
**Rejection reason:** <verbatim reasoning from critic verdict>

**Required fixes:**
- <fix item 1>
- <fix item N>
```

**`.github/implementation-progress.json` schema:**

```json
{
  "cycle_id": "string",
  "started_at": "ISO 8601",
  "last_updated": "ISO 8601",
  "steps": {
    "read_plan": "pending | done | failed",
    "read_conventions": "pending | done | failed",
    "write_tests_first": "pending | done | failed",
    "write_code": "pending | done | failed",
    "lint": "pending | done | failed",
    "type_check": "pending | done | failed",
    "unit_tests": "pending | done | failed",
    "explain_test_changes": "pending | done | failed",
    "complexity_check": "pending | done | failed",
    "conventions_check": "pending | done | failed",
    "submit_for_pattern_critic": "pending | done | failed"
  },
  "failed_step": "string | null",
  "failure_output": "string | null"
}
```

**`.github/pipeline-overrides.yaml` schema:**

```yaml
# All sections are optional. An absent file is equivalent to "no overrides, default entry point."
cycle_id: <string>          # must match the current cycle; otherwise the file is ignored

entry_point:
  start_at: refine | spec-critic | plan | implement | pattern-critic | scribe
  generate_mr_description: false  # default false — set to true to trigger /create-mr-description after Gate 2
  inline_inputs:             # provide artifacts directly when skipping the step that would have produced them
    requirements: |
      <inline markdown — used when start_at >= spec-critic and requirements.md does not exist>
    plan: |
      <inline markdown — used when start_at >= implement and implementation-plan.md does not exist>

overrides:
  - critic: spec-critic | pattern-critic
    check: <check name, e.g. "edge-cases" | "plan-adherence" | "knowledge-coverage">
    reason: "<one-sentence justification, recorded in rejection-log.md>"
    expires_after_cycles: 1  # how many cycles this override is valid for; default 1
```

Both critics MUST: (a) read this file before running checks, (b) treat any matching `(critic, check)` pair as `pass` for that check, (c) append an `OVERRIDDEN` entry to `rejection-log.md` recording the bypass. Overrides never silently pass — they are tracked.

---

## Partial Entry Points

The pipeline supports starting at any step. `/run-pipeline` reads `.github/pipeline-overrides.yaml > entry_point.start_at` (default: `refine`) and skips earlier steps.

| `start_at` | Skips | Requires |
|---|---|---|
| `refine` | nothing | a raw idea (default) |
| `spec-critic` | refine | `requirements.md` exists OR `inline_inputs.requirements` |
| `plan` | refine, spec-critic | APPROVED `requirements.md` OR `inline_inputs.requirements` + Dev attests to spec quality in the override file |
| `implement` | refine, spec-critic, plan | `implementation-plan.md` exists OR `inline_inputs.plan` |
| `pattern-critic` | everything up to implement | a diff already in the working tree |
| `scribe` | everything up to pattern-critic | a recently-APPROVED diff (no critic re-run; assumes manual approval) |

Starting past `spec-critic` without an `entry_point` override is forbidden — Dev must declare the bypass in the overrides file. This replaces the practice of commenting out checks.

---

## Decomposition Policy

The refiner assesses change size before drafting requirements. A change is **decomposable** when **any** of the following hold:

- Impact analysis identifies **more than 5 files** with non-trivial changes.
- The impact set spans **more than 2 cards** with non-trivial changes (the measurable form of "architectural boundaries").
- The change **introduces a new pattern** (a new state-management approach, new persistence convention, new error-handling convention).
- The change **modifies a shared contract consumed by more than 3 consumers** (per the cards' `public_contracts` / `depends_on` graph).

When decomposable, the refiner produces:

- `.github/requirements/requirements-index.md` — the index of sub-requirements with a dependency graph.
- `.github/requirements/<NN>-<slug>.md` — one file per sub-requirement, each independently passable through Gate 1.

Each sub-requirement runs its **own** RPI cycle. `/run-pipeline` walks the index in dependency order, pausing at gates for each sub-cycle.

The index schema:

```markdown
# Requirements Index: <title>

## Decomposition Rationale
<why this was split, citing the trigger from the policy above>

## Sub-Requirements
| Order | File | Title | Depends on | Estimated files |
|---|---|---|---|---|
| 1 | 01-<slug>.md | <title> | — | <N> |
| 2 | 02-<slug>.md | <title> | 1 | <N> |

## Cross-Cutting Acceptance
<criteria that only make sense across the whole set, run after all sub-cycles>

## Combined Knowledge References
- Tags: <union of sub-requirement tags>
- Knowledge updates expected: <cards/docs>
```

---

## Agent Inventory (6 total)

| Agent | Role | Model |
|---|---|---|
| `@refiner` | Requirements analysis and gap detection (kb-resolve-backed) | Claude Sonnet 4.6 |
| `@planner` | Technical implementation plan (card-constrained) | Claude Sonnet 4.6 |
| `@spec-critic` | Pre-implementation feasibility gate | Claude Sonnet 4.6 |
| `@pattern-critic` | Post-implementation standards gate (+ knowledge coverage) | Claude Opus 4.8 |
| `@implementer` | YAML rail executor — runs in isolated context window | Claude Sonnet 4.6 |
| `@scribe` | Knowledge layer + docs updater | Claude Sonnet 4.6 |

**`@pattern-critic` runs on Opus 4.8** because it is the last line of defense before code reaches a PR — a false APPROVED is a code quality failure. All other agents run on Sonnet 4.6.

**`@implementer` runs as an agent (not in-context)** so lint logs, test dumps, and file reads stay in its isolated context window. `/run-pipeline` invokes it via the `Agent` tool and receives only the IMPLEMENTER REPORT back.

### GHCP Model-Selection Note

GitHub Copilot in VS Code may ignore the `model:` field in an agent's `.agent.md` frontmatter. When invoking an agent directly, name the model explicitly in your request if the default model is not the one intended — e.g. *"Run `@pattern-critic` with Claude Opus 4.8."* The model column above is the source of truth.

---

## Prompt Inventory

| Prompt | Owns | Forbidden from |
|---|---|---|
| `/run-pipeline` | Chaining all pipeline steps; invoking gate-triage before each critic; pausing at gates; context-tracking between steps | Adding reasoning beyond what each step defines |
| `/gate-triage` | Mechanical structural validation before a critic invocation; returns PASS or STRUCTURAL_FAIL | Reasoning about quality, coherence, or correctness — that is the critic's job |
| `/refine-requirements` | Writing `requirements.md` (tags → confirm → kb-resolve) | Making code changes |
| `/create-implementation-plan` | Writing `implementation-plan.md` | Writing final code |
| `/implement-plan` | Writing code + tests, following the YAML rail | Modifying the plan or requirements |
| `/fix-rejection` | Applying pattern-critic required fixes, re-running downstream steps, resubmitting | Touching files outside the critic's required fixes |
| `/create-mr-description` | Generating a structured MR description from requirements + plan + diff | Editing any source file |
| `/explain-changes` | Answering questions about why specific changes were made, citing plan + diff | Speculating beyond documented sources |
| `/write-tests` | Standalone test authoring per the repo's test conventions | Writing to the knowledge layer |
| `/impact` | Lightweight impact brief (tags → resolve → brief) for questions that don't warrant the full pipeline | Making changes |
| `/new-card` | Scaffolding a knowledge card that passes kb:validate | Editing code |
| `/sync-cards` | Post-hoc knowledge repair outside a pipeline run (inside the pipeline this is `@scribe`'s job) | Editing code |

## Skill Inventory

| Skill | Purpose |
|---|---|
| `#code-analyzer` | Cyclomatic complexity + file-level deltas, JSON output (used by the rail and Gate 2) |

Upstream's `#wiki-init`, `#patterns-seed`, `#llm-wiki`, and `#project-map` are
NOT installed here — the knowledge layer (cards + manifest + `kb:drift`)
replaces them deterministically.

---

## Token Efficiency

The pipeline minimizes unnecessary token consumption without weakening quality gates.

### Gate triage: structural pre-screening before critics

`/run-pipeline` runs `/gate-triage` in-context before each critic invocation. Gate triage performs mechanical checks only (section headers present, test files in diff, no suppression comments, conventions corpus non-empty). If the artifact has a structural failure, the triage returns `STRUCTURAL_FAIL` immediately — no critic is invoked.

### Context isolation: `@implementer` as a subagent

`/run-pipeline` invokes `@implementer` via the `Agent` tool. The 11-step YAML rail — including all lint output, test dumps, and file reads — stays in the implementer's isolated context window. The orchestrator receives only the final IMPLEMENTER REPORT block (~1–2 KB).

### Progressive disclosure instead of lazy wiki reads

Upstream needed per-critic rules about which wiki files to read. Here the
knowledge layer's disclosure ladder does that job structurally: agents load the
resolved cards (~500 tokens each), follow `docs:` links only when relevant, and
never read code at analysis time. The conventions corpus auto-loads via
Copilot's own `applyTo` mechanism. Context cost scales with the task, not the
codebase.

### Context tracking between steps

After each agent's HANDOFF block, `/run-pipeline` writes a single structured line to its working context and discards the full report body:
`[STEP <N> <AGENT>] verdict=<...> artifact=<path> flags=<N>`
Report prose, reasoning, and intermediate output are never carried forward. The orchestrator routes on facts, not narrative.

### `@implementer`: self-contained agent (no prompt file pre-load)

`@implementer` contains the full 11-step YAML rail directly. When invoked via the `Agent` tool, it does not read `implement-plan.prompt.md` as a separate pre-flight step. The prompt file remains available for direct `/implement-plan` invocations (manual, non-pipeline use).

Step 10 (`conventions_check`) uses the conventions content already loaded in Step 2 — no re-read.

### Conditional clarifying questions

`@refiner` skips its upfront question round when the idea names specific modules and the resolved cards provide sufficient context. Residual unknowns go into `Open Questions` instead. The tag-confirmation ask always happens — it is one line, and it is what keeps retrieval auditable.

### Early exit on unhealthy knowledge layer

Every entry point runs `npm run kb:validate` first (~1s, zero dependencies). A failing layer rejects immediately rather than producing work built on stale knowledge.

### Error output truncation

Hard-block error output in IMPLEMENTER REPORT is capped at 50 lines. Full output is preserved in `.github/implementation-progress.json` for debugging.

### MR description: opt-in

`/create-mr-description` is skipped by default. Enable it by setting `generate_mr_description: true` in `pipeline-overrides.yaml` or by typing `mr` after Gate 2 approval.

---

## Golden Rules (enforced by `@pattern-critic` and `@spec-critic`)

1. **Atomic Skills** — one responsibility per skill. Reject any skill description containing "and".
2. **No Hallucinated Tools** — every `@agent`, `#skill`, or `npm run kb:*` reference must resolve to a real file.
3. **Metadata First** — agents need `name`, `description`, `tools`, `model`. Skills need `name`, `description`, `user-invocable`, `argument-hint`. Names are lowercase kebab-case.
4. **Dry Run** — every `run.py` supports `--dry-run` with no side effects.
5. **Complexity Ceiling** — no function above cyclomatic complexity 15 without an explicit `# complexity-exempt:` comment explaining why.
6. **Knowledge Before Merge** — a change that touches a card's `code:` paths, a public contract, or a dependency is **not complete** until `@scribe` has updated the corresponding card/doc and regenerated the manifest. `kb-guard` at Gate 2 and the pre-commit hook enforce this.
7. **Simplicity First** — write the minimum code that satisfies the acceptance criteria. No speculative abstractions, no single-use design patterns, no scope beyond the plan. If an abstraction serves only one call site today, it does not belong.

---

## What This System Does NOT Do

- No shadow production verification. That belongs in CI/CD, not in an IDE agent.
- No multi-layer router. Dev drives the pipeline directly; the pipeline is the routing.
- No redundant validation agent. Critics replaced it.
- No automatic PR creation or merging. `/create-mr-description` generates the description; you open the PR.
- No committed generated graphs. `kb:drift` output is compute-compare-discard; `manifest.json` is the only committed generated file.

---

## Trivial-Task Escape Hatch

For changes that are genuinely trivial — typo fix, variable rename, dependency version bump — skip the full pipeline. Make the edit, run tests, commit (the pre-commit hook still runs the kb checks). The full RPI pipeline exists for **behavioral changes**, not cosmetic ones.

Rule of thumb: if the change needs a test, it needs the pipeline.
