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

**Step 3 — populate the critical wiki files by hand.**
The auto-seed is a starting point, not a finish. Before running any RPI cycle, fill in at least:

- `.wiki/PATTERNS.md` — your naming, DI, error-handling, and test conventions.
- `.wiki/DEPENDENCIES.md` — current, deprecated, and banned libraries.
- `.wiki/DATA_MODELS.md` — key schemas.

Budget 30–60 minutes. This is a one-time cost and pays for itself on the first real task.

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

The refiner asks 3–5 clarifying questions, reads the wiki, and writes `.github/requirements/requirements.md` with testable acceptance criteria. No code is touched.

### Step 2 — GATE 1 (Spec Critic)

```
@spec-critic
```

Reads `requirements.md` + `.wiki/` and returns a **binary** verdict.

- **APPROVED** → pause for your approval, then continue.
- **REJECTED** → the critic names the single change that would unblock the spec. Fix `requirements.md` and re-run.

### Step 3 — Plan

```
/create-implementation-plan
```

The planner reads the approved spec + the full wiki and writes `.github/implementation-plan.md`: files to change, a test case per acceptance criterion, atomic implementation steps, and the `Wiki Updates Required` list.

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
- **REJECTED** → the critic lists the specific fixes in order. Re-run `/implement-plan` until the diff passes.

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

On any critic rejection you also decide: retry with the critic's fix, or abandon?

No other automatic pauses. Internal handoffs are direct — you invoke the next step yourself after each one completes.

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

The diagram at the top of this guide is the single source of truth for the visible flow. Key things to notice:

- **Center column** = the pipeline, top to bottom, driven directly by Dev.
- **Yellow sync bars** = the two places you are expected to respond.
- **Red "REJECTED" loops** on the right = what happens when a critic blocks.
- **Orange dashed arrows** to the wiki = read access. Agents read from these files.
- **Purple solid arrow** from `@scribe` to the wiki = write access. Only scribe writes.
- **Left panel** = skills, callable any time, from inside or outside the pipeline.
- **YAML rail callout** (bottom-left) = the deterministic 10-step sequence `/implement-plan` must follow.

---

## 8. Troubleshooting

**"Spec critic keeps rejecting with 'wiki missing'."**
`.wiki/` doesn't exist. Run `#wiki-init`. Populate `PATTERNS.md` and `DEPENDENCIES.md` by hand.

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

---

## 9. What this system does not do

- No shadow production traffic verification (that's CI/CD, not an IDE tool).
- No cross-repo orchestration.
- No automatic PR creation or merging — `/create-mr-description` generates the description; you open the PR.

If you want any of the removed capabilities from legacy `semiPilot/`, run both systems in parallel. They don't conflict.

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

`/implement-plan` writes and maintains a checkpoint file that tracks per-step status across the 10-step YAML rail. This file enables resuming a blocked run without re-executing steps that already passed.

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
    "complexity_check": "pending",
    "wiki_pattern_check": "pending",
    "submit_for_pattern_critic": "pending"
  },
  "failed_step": "unit_tests",
  "failure_output": "FAIL src/auth/auth.service.test.ts\n  ● AuthService › login › should return 401 on invalid password\n    Expected: 401\n    Received: 200"
}
```

This file is never committed — add `.github/implementation-progress.json` to `.gitignore`.
