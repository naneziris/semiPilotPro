# SemiPilot Pro — User Guide

A practical walkthrough of the system: what the full flow looks like, what you can use on its own, and when to reach for each piece.

![SemiPilot Pro flow diagram](docs/flow.png)

---

## 1. First-time setup (once per codebase)

SemiPilot Pro assumes a populated wiki. Without it, the critics have nothing to compare against and will fail loudly by design.

**Step 1 — install the system in your project.**
Copy the folder into `.github/` of your repo (or point your Copilot workspace at it):

```
your-project/
└── .github/
    ├── copilot-instructions.md
    ├── agents/
    ├── prompts/
    └── skills/
```

**Step 2 — bootstrap the wiki.**
From your project root:

```
#wiki-init
```

This scaffolds `.wiki/` with seven template files. `OVERVIEW.md` and `DATA_MODELS.md` get auto-seeded from detected manifests and schemas.

**Step 3 — seed `PATTERNS.md` from your existing code.**

```
#patterns-seed --dry-run    # inspect what it would write
#patterns-seed              # write it
```

Required on a non-empty codebase. `#patterns-seed` samples your source files and infers the dominant naming convention, DI style, error-handling pattern, import style, and test-file pattern. It writes these to `PATTERNS.md` so the Pattern Critic has something to enforce on the first cycle. Without this step the critic either rejects every diff or — more commonly — gets commented out, which defeats the system.

If a section is wrong, edit `PATTERNS.md` directly. This is the **only** wiki file you may edit by hand during bootstrap; `@scribe` owns it after the first successful cycle.

**Step 4 — fill in the remaining critical files.**
Before running any RPI cycle, also fill in:

- `.wiki/DEPENDENCIES.md` — current, deprecated, and banned libraries.
- `.wiki/DATA_MODELS.md` — key schemas (auto-seeded; verify and refine).

Budget 30 minutes. This is a one-time cost and pays for itself on the first real task.

---

## 2. The main user flow (RPI + Critics + Scribe)

Use this flow for any behavioral change — a feature, a non-trivial fix, anything that needs a test.

You can drive the pipeline in two ways:

- **Manual** — invoke each step yourself in the order shown below. Useful when you want to inspect or redirect between steps.
- **Auto** — run `/run-pipeline` once. It chains all steps automatically and pauses only at the two human sync gates, asking "approve" before moving past each gate.

The steps and gates are identical in both modes.

### Step 1 — Refine

```
/refine-requirements
```

The refiner does three things, in order:

1. **Asks 3–5 clarifying questions** in a single batched message and waits for your answers.
2. **Runs impact analysis** using `search` and `usages` on every symbol the change touches. The result is a populated `## Impact Analysis` section in the requirements file: consumers (with breakage-risk ratings), side-effect surfaces, and tests that exercise the touched surface. This is the step that catches refactors that would miss a `useEffect`, a context provider, or a hook subscription.
3. **Checks decomposition triggers.** If the change crosses more than 5 files, more than 2 architectural boundaries, introduces a new pattern, or modifies a shared API with more than 3 call sites, the refiner emits `requirements-index.md` plus one file per sub-requirement. Each sub-requirement runs its own RPI cycle.

Output: `.github/requirements/requirements.md` **or** `requirements-index.md` + sub-files. No code is touched.

### Step 2 — GATE 1 (Spec Critic)

```
@spec-critic
```

Reads the requirements + `.wiki/` and returns a **binary** verdict against nine checks (feasibility, edge cases, testability, circularity, scope coherence, impact-analysis coverage, decomposition compliance, …).

- **APPROVED** → pause for your approval, then continue.
- **REJECTED** → the critic names the single change that would unblock the spec. Fix the requirements and re-run.

### Step 3 — Plan

```
/create-implementation-plan
```

The planner reads the approved spec, the impact analysis, and the full wiki, then writes `.github/implementation-plan.md`: files to change, a test case per acceptance criterion, atomic implementation steps, and the `Wiki Updates Required` list. Every `high`-risk consumer from the impact analysis must appear in `Files to Change` — or be explicitly justified as "no change needed." For a `requirements-index.md` input, the planner produces one plan per sub-requirement.

### Step 4 — Implement

```
/implement-plan
```

This follows the **YAML rail** step-by-step. Every step hard-blocks on failure — the implementer posts the error verbatim and stops rather than silently continuing:

1. read_plan
2. read_wiki_patterns
3. **write_tests_first** (TDD red)
4. write_code
5. lint *(hard block on any error)*
6. **type_check** *(tsc --noEmit / mypy — hard block on any error)*
7. **unit_tests** *(hard block — posts verbatim failure output)*
8. **explain_test_changes** *(hard block — modified existing tests require a per-file reason citing the plan)*
9. complexity_check (runs `#code-analyzer`, threshold 15)
10. wiki_pattern_check
11. submit → `@pattern-critic`

The implementer reports every step. The pattern critic verifies the report against the rail before approving.

### Step 5 — GATE 2 (Pattern Critic)

```
@pattern-critic
```

Reads the diff against `.wiki/PATTERNS.md`, `DEPENDENCIES.md`, and `API.md`, verifies tests exist on disk, and runs `#code-analyzer` on changed files. Binary verdict.

- **APPROVED** → pause for your approval, then continue.
- **REJECTED** → the critic lists the specific fixes in order. Run `/fix-rejection` — it reads the rejection log, shows you what it will change, applies only those fixes, re-runs the downstream verification steps, and resubmits to `@pattern-critic`. Do not re-run `/implement-plan` from scratch.

**Mid-implementation scope expansion:** if `/implement-plan` discovers a file outside `Files to Change` that genuinely must be modified (typically because the impact analysis missed a consumer), it emits a `### SCOPE EXPANSION REQUEST` block and waits. You can approve inline or via `pipeline-overrides.yaml`. Approved expansions are recorded in the rejection log as `SCOPE_EXPANSION` entries and surface in the Pattern Critic's verdict — never silent.

### Step 6 — MR Description (optional)

```
/create-mr-description
```

Reads `requirements.md`, `implementation-plan.md`, and the git diff, then produces a structured MR description ready to paste into your PR. Run this after Gate 2 approval and before Scribe. Skip it if you prefer to write the description yourself.

### Step 7 — Scribe

```
@scribe
```

Appends to the `.wiki/` files the plan authorized (ADR, schema delta, API change, etc.) and writes a user-facing line in `CHANGELOG.md`. Scribe is the **only** agent that writes to `.wiki/`.

---

## 3. The two human sync points

The pipeline pauses for your explicit approval exactly twice per successful cycle:

| Gate | When | What you're deciding |
|---|---|---|
| **Sync 1** | After Spec Critic APPROVED | Does this spec reflect what I actually want? |
| **Sync 2** | After Pattern Critic APPROVED | Is the diff the change I want to merge? |

On any critic rejection you also decide: apply the fix or abandon?

When running manually, you invoke each step yourself. When using `/run-pipeline`, handoffs between steps are automatic — it pauses only at the two sync gates and on any critic rejection.

---

## 4. Using components on their own

Everything in SemiPilot Pro is designed to be useful in isolation.

### Agents

| Agent | Use on its own when… |
|---|---|
| `@refiner` | You have a vague idea and want a testable spec written, but you're not ready to implement. Output is `requirements.md`. |
| `@planner` | You already have a clean spec (yours or someone else's) and just want a concrete implementation plan. |
| `@spec-critic` | You want a second opinion on whether a spec is feasible against your current architecture and data model. Great for PR-review-style spec reviews. |
| `@pattern-critic` | Run it on any diff to catch pattern violations, banned dependencies, or complexity regressions. Works even if the diff wasn't produced by `/implement-plan`. |
| `@scribe` | You made a change manually and want the `.wiki/` updated. Hand it the diff and the scribe appends the right entries. |

### Prompts

| Prompt | Use on its own when… |
|---|---|
| `/run-pipeline` | You want to start a full cycle and let the system handle all handoffs. It pauses at Gate 1 and Gate 2 for your approval; everything else is automatic. |
| `/refine-requirements` | Shortest path to a clean spec. Identical to invoking `@refiner`. |
| `/create-implementation-plan` | You have an approved spec from any source (including hand-written) and want a plan without running Gate 1. |
| `/implement-plan` | You already have a plan and want code written under the YAML rail — tests first, type-checked, linted, complexity-checked. |
| `/fix-rejection` | After a Gate 2 REJECTION, applies only the critic's required fixes, re-runs the downstream verification steps (lint, type_check, unit_tests, explain_test_changes, complexity_check, wiki_pattern_check), and resubmits to `@pattern-critic`. Do not re-run `/implement-plan` from scratch. |
| `/create-mr-description` | After Gate 2 approval, generates a structured MR description (What / Why / Changes / Tests / Acceptance Criteria / Risks / Notes for Reviewer) ready to paste into your PR. |
| `/explain-changes` | Ask a specific question about why a file, function, or test was changed. Answers cite `requirements.md`, `implementation-plan.md`, or the diff — no speculation. |

### Skills

| Skill | Use on its own when… |
|---|---|
| `#wiki-init` | Bootstrapping the wiki on a new codebase, or re-seeding a specific file with `--force`. |
| `#code-analyzer` | Spot-checking a single file for complexity violations. Returns JSON; fine to pipe into CI. |
| `#llm-wiki concat` | Building a context document to ask questions about the codebase — wiki only, or wiki + source. See Section 10 for a full walkthrough. |
| `#llm-wiki ingest` / `query` | Semantic search over a large codebase where `concat` would exceed the word budget. See Section 10. |
| `#project-map` | Getting a quick markdown table of monorepo packages and their internal dependency graph. |

---

## 5. Composition patterns

The pieces are more useful together than alone. Common recipes:

**"I want a spec and a plan, but I'll write the code myself."**
`/refine-requirements` → `@spec-critic` → `/create-implementation-plan`. Stop there. Implement by hand.

**"I have code I want reviewed against our standards."**
`@pattern-critic` on the diff. No spec or plan required.

**"I want to share project context with another LLM."**
`#llm-wiki concat` → paste the output into whatever model you're using.

**"I'm onboarding a new engineer."**
Point them at `.wiki/OVERVIEW.md`, `ARCH_DECISIONS.md`, and `PATTERNS.md`. That's the tour.

**"Wiki drift is making the critics noisy."**
Run `@scribe` with a backfill request: "audit the last 10 PRs and update `.wiki/ARCH_DECISIONS.md` accordingly."

**"A human reviewer caught a mistake. How do I make sure it never happens again?"**
Encode the rule in the wiki — the critics enforce whatever is written there, automatically, on every future diff.

Route the finding to the right file:

| Finding | Where to encode it |
|---|---|
| Naming / style / test convention | `.wiki/PATTERNS.md` |
| Wrong library used | `.wiki/DEPENDENCIES.md` (mark as deprecated or banned) |
| Architectural mistake | `.wiki/ARCH_DECISIONS.md` (add an ADR explaining the constraint) |
| Wrong API contract | `.wiki/API.md` |

To formalize the update, hand the finding to `@scribe`:
*"A human reviewer flagged that we should never call `UserService` directly from a controller. Add a `PATTERNS.md` entry prohibiting it."*

Once the rule is in the wiki, `@pattern-critic` will block any future diff that repeats the mistake.

**"I want to improve the system itself."**
Treat SemiPilot Pro as the codebase being modified. For non-trivial changes (a new gate, a changed rail step, a new agent), run the full pipeline. For smaller improvements (tightening a convention, banning a library, adjusting a complexity threshold): update the relevant wiki file directly, then hand the change to `@scribe` to log it in `ARCH_DECISIONS.md`.

---

## 6. When to skip the pipeline

Not everything deserves RPI + Critics + Scribe. Skip it for:

- Typo fixes
- Variable renames
- Dependency version bumps (unless upgrading across a major version)
- Comment-only changes

Rule of thumb: **if the change needs a test, it needs the pipeline.**

For a skip, just edit the code, run tests, and commit. The wiki doesn't need an update unless you touched something on the `Wiki Updates Required` list.

---

## 7. Reading the flow diagram

The diagram at the top of this guide is the single source of truth for the visible flow. It is intentionally minimal — one column, top to bottom.

- **Blue boxes** = pipeline agents and prompts.
- **Red boxes** = the two critic gates (Gate 1 = spec, Gate 2 = pattern).
- **Amber boxes** = human sync points. You respond to exactly two per successful cycle.
- **Purple box** = `@scribe`. The teal underline marks it as the only writer to `.wiki/`.
- **Slate boxes** = start (`User Idea`) and end (`Change Complete`).
- **Red dashed arrows on the left** = critic rejections. Spec rejection loops back to `@refiner`; pattern rejection loops back to `/implement-plan` (via `/fix-rejection`).
- **Italic notes on the right** = what each step produces or consumes.

Not pictured (intentionally — they add complexity and live in the docs instead):

- The 11-step YAML rail inside `/implement-plan` — see Section 2, Step 4.
- The five reusable skills (`#wiki-init`, `#patterns-seed`, `#code-analyzer`, `#llm-wiki`, `#project-map`) — they are callable from anywhere, not part of the spine.
- The override and decomposition machinery — see Sections 15 and 16.

---

## 8. Troubleshooting

**"Spec critic keeps rejecting with 'wiki missing'."**
`.wiki/` doesn't exist. Run `#wiki-init`, then `#patterns-seed` (on an existing codebase), then populate `DEPENDENCIES.md` by hand.

**"Pattern critic rejects everything because `PATTERNS.md` is empty / I find myself commenting out critic checks."**
This is the bootstrap deadlock. Run `#patterns-seed` from the project root — it scans the existing code and seeds `PATTERNS.md` with the conventions it finds. If a section is wrong, edit it directly. Stop commenting out checks; declare the bypass in `.github/pipeline-overrides.yaml` instead (see Section 15).

**"Pattern critic rejects on a naming convention I don't care about."**
The critic only enforces what's in `.wiki/PATTERNS.md`. Remove or change the convention there — don't argue with the critic.

**"The implementer keeps hitting complexity threshold."**
Two options: refactor the function (the system's preference), or mark it `# complexity-exempt: <reason>` if the complexity is genuinely justified. The critic will respect the exemption tag.

**"I want to use a library that's banned in `DEPENDENCIES.md`."**
Either amend the wiki (open a plan that updates it — critics can authorize their own rules changing) or argue the case with Dev first. Don't silently bypass.

**"`/implement-plan` blocked on type_check / unit_tests."**
This is working as intended. Read the verbatim error output the implementer posted. If the failure is in production code, treat it as a bug (see Section 11). If it's in a test file, fix the test before re-running the rail step.

**"The implementer reported a step as 'done' but the diff contradicts it."**
This is a rail violation — `@pattern-critic` will catch it at Gate 2 via the YAML rail completeness check. If you notice it before running the critic, re-run `/implement-plan` from the blocked step.

**"I want to understand why the spec critic keeps rejecting this cycle."**
Read `.github/rejection-log.md`. Every REJECTED verdict is appended there with a timestamp, the verbatim reasoning, and the exact fix required. Sort by Cycle to see if the same root cause is recurring.

**"`/implement-plan` blocked mid-run — how do I resume without re-running completed steps?"**
The progress file `.github/implementation-progress.json` tracks each step's status. Re-invoke `/implement-plan` — it reads the file, sees which steps are `"done"`, and resumes from the first `"pending"` or `"failed"` step. No manual intervention needed.

**"I want to restart the implementation from scratch, ignoring the saved progress."**
Delete `.github/implementation-progress.json`. The next `/implement-plan` run will start fresh and overwrite the file.

**"Pattern critic rejected my diff — what do I do?"**
Run `/fix-rejection`. It reads the latest entry in `.github/rejection-log.md`, shows you the required fixes and which files it will touch, waits for your `confirm`, applies only those changes, re-runs lint/type_check/unit_tests/explain_test_changes/complexity_check/wiki_pattern_check, and resubmits to `@pattern-critic`. Do not delete the checkpoint and re-run `/implement-plan` from scratch — that reruns all 11 steps unnecessarily.

---

## 9. What this system does not do

- No shadow production traffic verification (that's CI/CD, not an IDE tool).
- No cross-repo orchestration.
- No automatic PR creation or merging — `/create-mr-description` generates the description; you open the PR.

---

## 10. Asking questions about the codebase (#llm-wiki)

**Important:** `#llm-wiki` does not answer your question. It builds a context document. You then ask Copilot (or any LLM) while referencing that document. This two-step workflow is the key to using it correctly.

### Step 1 — build the context file

```bash
# Wiki files only → fast, no dependencies
#llm-wiki concat

# Wiki + all source files → needed for questions about runtime behavior
#llm-wiki concat --include-source

# Scoped to a specific directory → smaller, faster for targeted questions
#llm-wiki concat --include-source --source src/frontend
```

All three write to `.wiki/wiki-context.md`.

### Step 2 — ask Copilot referencing the context

Open `.wiki/wiki-context.md` in your editor, then ask in Copilot Chat:

> `@workspace Using the context in wiki-context.md, <your question here>.`

### Which mode to use

| Question type | Mode |
|---|---|
| *Why did we do X?* — architecture, decisions, patterns | `concat` (wiki only) |
| *How does X work?* — runtime behavior, data flow, component logic | `concat --include-source` |
| Large codebase where `--include-source` gets truncated | `ingest` + `query` (FAISS) |

The word budget for `concat` is 40 000 words. If the output file says `[truncated]`, switch to a scoped `--source` or to FAISS mode.

---

### Concrete examples

**"Explain the user flow of the checkout feature."**

```bash
#llm-wiki concat
```

Then in Copilot:
> `@workspace Using wiki-context.md, explain the user flow of the checkout feature step by step, from the cart page through to order confirmation.`

---

**"How does the user get authenticated?"**

```bash
#llm-wiki concat --include-source
```

Then:
> `@workspace Using wiki-context.md, trace how a user gets authenticated — from the login form submit to the session token being set. Name the specific functions and files involved.`

---

**"There is an AccountsWidget that displays a list of accounts. How does it fetch its data? And why might it re-render multiple times?"**

```bash
# Option A — small/medium codebase:
#llm-wiki concat --include-source

# Option B — large codebase, target the relevant area:
#llm-wiki ingest --source . --index-dir .wiki/.index   # one-time setup
#llm-wiki query --index-dir .wiki/.index --q "AccountsWidget data fetching re-render"
```

With `concat --include-source`, ask Copilot:
> `@workspace In wiki-context.md, find AccountsWidget. How does it fetch account data — what API call, what state management? List every reason it could trigger a re-render.`

With FAISS, the `query` command prints the 5 most relevant code chunks to your terminal. Paste those chunks into Copilot and ask the same question.

---

**"What AJAX calls does the application need in order to render the homepage without an error?"**

```bash
# Scoped to the frontend:
#llm-wiki concat --include-source --source src/frontend

# Or FAISS for a targeted query:
#llm-wiki query --index-dir .wiki/.index --q "homepage API calls requests render"
```

Then in Copilot:
> `@workspace In wiki-context.md, list every API call made during homepage render. Which are blocking (the page won't render without them)? Which can fail silently? What happens if any of the blocking calls return an error?`

---

### FAISS setup (one-time, large codebases only)

```bash
pip install sentence-transformers faiss-cpu
#llm-wiki ingest --source . --index-dir .wiki/.index
```

Re-run `ingest` only when the codebase changes significantly. Queries are instant after that.

---

## 11. Finding and fixing a bug

The single decision: **does the fix need a test?**

### Trivial fix (no test required)

For an obvious off-by-one, a wrong string, a missing null guard — if you can see the fix and prove it with existing tests:

1. Edit the code.
2. Run the existing test suite.
3. Commit.

Skip the pipeline entirely. See Section 6.

### Non-trivial fix (needs a test to prove it)

Use the full pipeline, treating the bug as a behavioral specification:

**Step 1 — `/refine-requirements`**
Describe the bug as a spec: *"Currently X happens when Y. It should do Z."* The refiner writes `requirements.md` with a failing acceptance criterion — a test that will prove the bug is fixed.

**Step 2 — `@spec-critic`**
Gate 1 confirms the fix is architecturally sound and doesn't contradict the wiki. A well-scoped bug fix almost always passes first try.

**Step 3 — `/create-implementation-plan`**
The planner reads the wiki and the spec, identifies the root cause location, and writes atomic steps. The plan names the specific file and function to change — not just "fix the bug."

**Step 4 — `/implement-plan`**
Writes the failing test first (red), then makes it pass (green), lints, type-checks, runs the full suite. If the test suite was already broken before your fix, the YAML rail will surface it here — the implementer hard-blocks on unit_tests and posts the verbatim failure. That output is your diagnostic.

**Step 5 — `@pattern-critic`**
Gate 2 confirms the fix doesn't violate patterns or introduce a new dependency while patching the bug.

**Step 6 — `@scribe`**
If the bug revealed an undocumented edge case, invariant, or constraint, `@scribe` adds it to the wiki so the critics catch it in future. Example: *"The bug revealed that `TransactionService` must never be called outside a database transaction. Add that to `PATTERNS.md`."*

### Bug surfaced by a failing test (not yet investigated)

If `/implement-plan` blocks at `unit_tests` and you don't know whether the failure is in the test or the production code:

1. Read the verbatim failure output the implementer posted.
2. **If the assertion is correct and the code is wrong** → the test found a real bug. Abandon the current `/implement-plan` run. Start a new `/refine-requirements` cycle describing the bug. This keeps the two changes separate and reviewable.
3. **If the test assertion is stale** (the test was written against old behavior that was intentionally changed) → fix the test file only, then re-run the blocked rail step.

Do not fix production code and update a stale test in the same implementation run. Two separate issues deserve two separate cycles.

Rule of thumb: **if the fix needs a test, it needs the pipeline.**

---

## 12. Creating a new agent

There is no `@new-agent` agent in SemiPilot Pro — it was cut intentionally to keep the system small. Creating an agent is a manual, four-step process.

### Step 1 — pick a template

Copy the agent most similar to what you need from [`agents/`](agents/):

| What you're building | Template to copy |
|---|---|
| A gate — makes a binary APPROVED / REJECTED call | `agents/spec-critic.agent.md` |
| A writer — reads inputs and produces a document or update | `agents/scribe.agent.md` |
| A planner / analyst — reasons about a problem and outputs a structured plan | `agents/planner.agent.md` |

### Step 2 — fill in required metadata

Every agent file must have these four fields at the top (Golden Rule #3 from `copilot-instructions.md`):

```yaml
name: my-agent               # lowercase kebab-case
description: one sentence, one responsibility — no "and"
tools: [tool-a, tool-b]      # only tools that actually resolve to real files
model: claude-sonnet-4-6     # Opus for gates, Sonnet for workers
```

Do not list a tool that doesn't exist. The pattern critic will reject it.

### Step 3 — declare it in copilot-instructions.md

Add a row to the Agent Inventory table in [`copilot-instructions.md`](copilot-instructions.md) under the correct model. This is how the system's inventory stays accurate and how humans discover the agent.

### Step 4 — validate it through the pipeline

Run the new agent through the pipeline as if it were a feature:
```
/refine-requirements  →  @spec-critic  →  /create-implementation-plan  →  /implement-plan  →  @pattern-critic
```

The critics will catch hallucinated tool references, missing metadata, naming violations, and any complexity problems in the agent's logic.

### Agent vs. prompt vs. skill — which to build?

| The thing you need… | Build a… |
|---|---|
| Reasons, decides, makes a gate call | Agent |
| Executes a deterministic sequence of file edits | Prompt |
| Runs a standalone script, returns JSON or text | Skill |

If you're unsure, default to a prompt. Agents are for things that genuinely need to *reason before deciding*.

---

## 13. The rejection log (`.github/rejection-log.md`)

Every time `@spec-critic` or `@pattern-critic` returns a REJECTED verdict, the critic appends a structured entry to `.github/rejection-log.md`. The file is created on first rejection and is append-only — entries are never modified or deleted.

**What each entry contains:**

- **Timestamp** — ISO 8601 datetime of the rejection.
- **Critic** — which gate issued the rejection (`spec-critic` or `pattern-critic`).
- **Cycle** — a short identifier for the requirements or implementation cycle. Derived from the plan/requirements filename stem, or `YYYY-MM-DD` if the file uses the default name.
- **Rejection reason** — verbatim from the critic's Reasoning field. The exact language the critic used.
- **Required fixes** — bullet list of the concrete changes that would unblock the next attempt.

**Sample entry:**

```
**Timestamp:** 2025-03-12T09:14:22Z
**Critic:** spec-critic
**Cycle:** 2025-03-12
**Rejection reason:** The spec requires a `subscription_tier` field that does not exist in the current `User` schema in DATA_MODELS.md. The field must be added before this spec can proceed.

**Required fixes:**
- Add `subscription_tier: enum(free, pro, enterprise)` to the User model in DATA_MODELS.md.
```

**How to use it:**

- **Debugging repeated failures.** If a cycle keeps getting rejected at the same gate, read the log. The same root cause appearing across multiple entries points to a structural gap in the wiki or a misunderstood constraint.
- **Scribe input.** When running `@scribe` at the end of a release, hand it the rejection log: `"Read .github/rejection-log.md and summarize any recurring rejection patterns in the CHANGELOG."` This converts operational history into durable architectural knowledge.
- **Onboarding.** New team members can read the log to understand which constraints the project enforces in practice and which ones have already caused rework.

`@scribe` does not write to this file. The critics own it exclusively.

---

## 14. Implementation checkpoint (`.github/implementation-progress.json`)

`/implement-plan` writes and maintains a checkpoint file that tracks per-step status across the 11-step YAML rail. This file enables resuming a blocked run without re-executing steps that already passed.

**How resume works:**

1. Re-invoke `/implement-plan` after fixing whatever caused the block.
2. The implementer reads `.github/implementation-progress.json` and checks the `cycle_id`.
3. If the `cycle_id` matches the current plan, it skips all steps marked `"done"` and resumes from the first `"pending"` or `"failed"` step.
4. The report at the end will note which steps were skipped.

**cycle_id derivation** (deterministic, no user input needed):
- If `implementation-plan.md` has a `cycle_id:` key in its YAML frontmatter, that value is used.
- If the filename is not `implementation-plan.md` (e.g., a descriptively named file), the filename stem is used.
- Otherwise, the `cycle_id` is `implementation-plan`.

**Force a fresh start:**
Delete `.github/implementation-progress.json`. The next run starts from step 1 regardless of what was previously done.

**What the file looks like mid-run (blocked at `unit_tests`):**

```json
{
  "cycle_id": "implementation-plan",
  "started_at": "2025-03-12T10:00:00Z",
  "last_updated": "2025-03-12T10:18:43Z",
  "steps": {
    "read_plan": "done",
    "read_wiki_patterns": "done",
    "write_tests_first": "done",
    "write_code": "done",
    "lint": "done",
    "type_check": "done",
    "unit_tests": "failed",
    "explain_test_changes": "pending",
    "complexity_check": "pending",
    "wiki_pattern_check": "pending",
    "submit_for_pattern_critic": "pending"
  },
  "failed_step": "unit_tests",
  "failure_output": "FAIL src/auth/auth.service.test.ts\n  ● AuthService › login › should return 401 on invalid password\n    Expected: 401\n    Received: 200"
}
```

This file is never committed — add `.github/implementation-progress.json` to `.gitignore`.

---

## 15. Pipeline overrides (`.github/pipeline-overrides.yaml`)

The override file replaces the practice of commenting out critic checks to get past a blocked gate. Every bypass is **declared** in this file and **recorded** in the rejection log. There is no silent override.

**When to use it:**

- A critic is rejecting on a check that genuinely does not apply to this cycle (e.g., the impact-analysis check on a one-line copy fix).
- You want to start the pipeline mid-flow (you already have a hand-written plan and don't need refine or spec-critic).
- You're running autonomously and need to pre-approve an expected scope expansion.

**File schema** (all sections optional):

```yaml
cycle_id: 2025-03-12-checkout-fix   # must match the current cycle; otherwise the file is ignored

entry_point:
  start_at: plan                    # refine | spec-critic | plan | implement | pattern-critic | scribe
  pauses: at-gates                  # none | at-gates (default) | after-each-step
  inline_inputs:
    plan: |
      # Implementation Plan: ...
      <inline markdown, written to .github/implementation-plan.md before the pipeline runs>

overrides:
  - critic: spec-critic
    check: edge-cases
    reason: "Single-line copy change; no edge cases apply."
    expires_after_cycles: 1
  - critic: pattern-critic
    check: plan-adherence
    reason: "Approved scope expansion for src/auth/session.ts — surfaced via SCOPE EXPANSION REQUEST."
    expires_after_cycles: 1
```

**How it gets enforced:**

- Both critics read the file before running their checks. Matching `(critic, check)` pairs are marked `overridden` (not `pass`) in the verdict.
- Each honored override appends an `OVERRIDDEN` entry to `.github/rejection-log.md` with the verbatim reason.
- A wrong `cycle_id` causes the file to be ignored (with a warning) — stale overrides cannot persist across cycles.
- `@scribe` reads `OVERRIDDEN` entries when writing the CHANGELOG and reports them at release time.

**Rule of thumb:** if you would have commented out a critic check, write an override entry instead.

---

## 16. Partial entry points (start mid-pipeline)

The pipeline does not have to start at `/refine-requirements`. You can begin at any step by setting `entry_point.start_at` in `pipeline-overrides.yaml`.

| `start_at` | Skips | Required input |
|---|---|---|
| `refine` | nothing | a raw idea (default) |
| `spec-critic` | refine | `requirements.md` exists OR `inline_inputs.requirements` |
| `plan` | refine, spec-critic | APPROVED `requirements.md` OR `inline_inputs.requirements` |
| `implement` | refine, spec-critic, plan | `implementation-plan.md` exists OR `inline_inputs.plan` |
| `pattern-critic` | everything up to implement | a diff already in the working tree |
| `scribe` | everything up to pattern-critic | a recently-approved diff |

**Example — "I have a plan; just implement it":**

```yaml
cycle_id: 2025-03-12-hotfix
entry_point:
  start_at: implement
  pauses: at-gates
```

`/run-pipeline` reads this, jumps to `/implement-plan`, runs the YAML rail, hands off to `@pattern-critic`, pauses at Gate 2 for your approval, then runs `@scribe`.

**Example — "Run autonomously, no pauses, override the edge-cases check":**

```yaml
cycle_id: 2025-03-12-typo
entry_point:
  pauses: none
overrides:
  - critic: spec-critic
    check: edge-cases
    reason: "Single-character typo fix; no edge cases."
```

Use `pauses: none` only when overrides cover every potential rejection — otherwise the pipeline will stop the moment a check fails.

---

## 17. Decomposition: when one requirement becomes many

`@refiner` automatically decomposes a change into multiple sub-requirements when **any** of the following hold (computed from the Impact Analysis):

- More than 5 files with non-trivial changes.
- More than 2 architectural boundaries crossed.
- Introduces a new pattern (new state management, new DI style, new error handling).
- Modifies a shared API consumed by more than 3 call sites.

**What the output looks like:**

Instead of `requirements.md`, you get:

```
.github/requirements/
├── requirements-index.md
├── 01-extract-state-to-context.md
├── 02-migrate-consumer-a.md
├── 03-migrate-consumer-b.md
└── 04-remove-old-reducer.md
```

`requirements-index.md` lists the sub-requirements in dependency order:

```markdown
# Requirements Index: Move auth state from reducer to context

## Decomposition Rationale
Impact analysis identified 8 consumers across 2 architectural boundaries.
Introduces a new state-management pattern (Context+useEffect, replacing useReducer).

## Sub-Requirements
| Order | File | Title | Depends on | Estimated files |
|---|---|---|---|---|
| 1 | 01-extract-state-to-context.md | Add AuthContext provider | — | 2 |
| 2 | 02-migrate-consumer-a.md | Migrate LoginPanel | 1 | 1 |
| 3 | 03-migrate-consumer-b.md | Migrate UserBadge | 1 | 1 |
| 4 | 04-remove-old-reducer.md | Delete legacy reducer | 2, 3 | 3 |

## Cross-Cutting Acceptance
- All auth tests still pass with the new context provider.
- No imports of `authReducer` remain in the tree after sub-cycle 4.
```

**How the pipeline walks it:**

`/run-pipeline` walks the index in dependency order. Each sub-requirement runs its **own** full RPI cycle: plan → implement → pattern-critic → scribe. Gates pause as configured. After the last sub-cycle, the orchestrator runs any `Cross-Cutting Acceptance` criteria.

**Why decomposition matters:**

A 50-file refactor done as one cycle produces an unverifiable plan and a diff too large to review meaningfully. Decomposition turns it into N small, independently verifiable changes — each with its own tests, its own gate pass, and its own wiki update. The total work is the same; the blast radius per cycle is much smaller.

**Forcing or suppressing decomposition:**

- If you want to force decomposition on a borderline case, ask `@refiner` directly: "Decompose this even though it only touches 4 files — I want each consumer migration separately reviewable."
- If `@refiner` decomposes but you genuinely want one cycle, override the spec-critic's decomposition check in `pipeline-overrides.yaml` and the index file collapses into a single requirements file.

---

## 18. Impact analysis: what it is and what to verify

The `## Impact Analysis` section in `requirements.md` is where most refactor failures get caught — or missed. Before approving a spec at Gate 1, read this section critically.

**What `@refiner` produces:**

- A list of symbols and modules the change touches.
- A **Consumers** table: every caller, subscriber, or mocker with a `low / medium / high` breakage-risk rating.
- A list of side-effect surfaces: state, context providers, event handlers, lifecycle hooks (e.g., `useEffect`), subscriptions.
- A list of tests that exercise the touched surface.
- A `Confidence: high | medium | low` rating.

**What to check when reviewing:**

- **Every `high`-risk consumer should appear in either the plan's `Files to Change` or the requirements' `Out of Scope`.** A high-risk consumer that's not addressed anywhere is a side effect waiting to break.
- **Side-effect surfaces are listed, not "none" by default.** If the refiner wrote "none" for a change involving React hooks, that's a red flag — push back.
- **Confidence is `high` for non-trivial changes.** `medium` or `low` is fine but the Open Questions section should name the specific unknowns.

**What to do when impact analysis is wrong:**

- If a consumer is missing → reply to `@refiner`: "You missed `<file>` which imports `<symbol>`. Re-run the analysis." The refiner re-traces.
- If a side-effect surface is missing → same approach.
- If decomposition was triggered but the breakdown is wrong → reply with the corrected dependency order; `@refiner` rewrites the index.

**Why this exists:**

Previous failures in real refactors (e.g., moving auth state from `useReducer` to a context provider) typically came from the refiner not tracing the call graph. Impact analysis is a mandatory step now, and the spec-critic rejects shallow analyses. If a side effect breaks in production, the rejection log should show whether the impact analysis caught it (the system worked) or missed it (the heuristics need strengthening).
