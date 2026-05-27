# SemiPilot Pro — OpenCode User Guide

A practical walkthrough of using the SemiPilot Pro agentic pipeline with [OpenCode](https://opencode.ai). This guide is written for building a **new app from scratch**.

---

## 1. Installation and setup

### 1.1 Install OpenCode

```bash
npm install -g opencode-ai
```

Verify it works:

```bash
opencode --version
```

### 1.2 Set your API key

OpenCode calls the Anthropic API directly. Set the key in your shell profile (`.zshrc`, `.bashrc`):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

OpenCode also supports `.env` files in the project root. Never commit the key.

### 1.3 Create your new project folder

```bash
mkdir my-app && cd my-app
git init
```

### 1.4 Deploy the SemiPilot Pro files

From the `semiPilotPro` repo, copy the OpenCode assets into your new project:

```bash
# System prompt — read by OpenCode on every session
cp path/to/semiPilotPro/opencode/AGENTS.md ./AGENTS.md

# Default model config
cp path/to/semiPilotPro/opencode/opencode.json ./opencode.json

# Agents and commands
mkdir -p .opencode/agents .opencode/commands
cp path/to/semiPilotPro/opencode/agents/*.md  .opencode/agents/
cp path/to/semiPilotPro/opencode/commands/*.md .opencode/commands/
```

Your project structure should now look like:

```
my-app/
├── AGENTS.md
├── opencode.json
└── .opencode/
    ├── agents/
    │   ├── refiner.md
    │   ├── spec-critic.md
    │   ├── planner.md
    │   ├── pattern-critic.md
    │   └── scribe.md
    └── commands/
        ├── run-pipeline.md
        ├── implement-plan.md
        ├── refine-requirements.md
        ├── create-implementation-plan.md
        ├── fix-rejection.md
        ├── write-tests.md
        ├── create-mr-description.md
        ├── explain-changes.md
        ├── wiki-init.md
        ├── patterns-seed.md
        ├── code-analyzer.md
        ├── project-map.md
        └── llm-wiki.md
```

Also copy the skills folder (Python scripts needed by commands):

```bash
cp -r path/to/semiPilotPro/skills ./skills
```

### 1.5 Add gitignore entries

```bash
cat >> .gitignore << 'EOF'
.github/implementation-progress.json
.wiki/.index/
EOF
```

### 1.6 Start OpenCode

```bash
opencode
```

You'll see the TUI. The system prompt from `AGENTS.md` is loaded automatically.

---

## 2. First-time wiki bootstrap (new project)

The pipeline's critics (`@spec-critic`, `@pattern-critic`) both read the wiki before making decisions. On a brand-new project the wiki doesn't exist yet — you need to scaffold it first. This is a one-time step.

### Step 1 — Initialize the wiki

In the OpenCode chat, type:

```
/wiki-init
```

This creates `.wiki/` with seven template files:

| File | Purpose |
|---|---|
| `OVERVIEW.md` | Tech stack, project purpose, team conventions |
| `ARCH_DECISIONS.md` | Architecture Decision Records |
| `DATA_MODELS.md` | Schemas, key types, relationships |
| `PATTERNS.md` | Naming conventions, DI patterns, test standards |
| `DEPENDENCIES.md` | Current / deprecated / banned libraries |
| `API.md` | Public API signatures and contracts |
| `CHANGELOG.md` | User-facing: what changed and why |

If a `package.json`, `pyproject.toml`, or similar manifest exists, the script seeds `OVERVIEW.md` and `DATA_MODELS.md` automatically. Since this is a new project the files are mostly templates — that's fine.

### Step 2 — Fill in the critical files by hand

Before your first pipeline cycle, fill in at minimum:

**`.wiki/OVERVIEW.md`** — one paragraph describing what you're building and the tech stack. Example:
```
A task management API built with FastAPI and PostgreSQL.
TypeScript frontend with React + Vite. Monorepo with pnpm workspaces.
```

**`.wiki/DEPENDENCIES.md`** — list your dependencies in three sections:
```markdown
## Current
- fastapi 0.100+
- sqlalchemy 2.0+
- react 18+
- vite 5+

## Deprecated
(none yet)

## Banned
(none yet)
```

**`.wiki/PATTERNS.md`** — on a brand-new project, start with your intended conventions:
```markdown
## Naming
- Files: kebab-case (e.g. `user-service.ts`)
- Functions: camelCase
- Classes: PascalCase
- DB tables: snake_case

## Tests
- Framework: vitest
- Location: co-located with source (e.g. `user-service.test.ts`)
- Structure: describe/it, AAA pattern
```

> **Tip:** Don't overthink `PATTERNS.md` on a new project. Write the conventions you intend to follow and let `@scribe` refine it as the codebase grows. What matters is that it's non-empty so `@pattern-critic` has something to enforce.

**`.wiki/DATA_MODELS.md`** — your initial schemas. Even a rough ERD in markdown is enough:
```markdown
## User
- id: UUID (PK)
- email: string (unique)
- created_at: timestamp
```

### Step 3 — Commit the wiki skeleton

```bash
git add .wiki/
git commit -m "Add wiki skeleton"
```

Now you're ready for the first pipeline cycle.

---

## 3. How OpenCode commands and agents work

Before walking the pipeline, understand how OpenCode handles the two building blocks.

### Commands (`/command-name`)

Commands are markdown files in `.opencode/commands/`. When you type `/run-pipeline` in the OpenCode chat, OpenCode loads that file's content as a prompt and runs it in the current session. Think of them as named system prompts you can invoke by name.

**Key difference from Claude Code:** Commands in OpenCode run **in the current session context** — they don't spawn new isolated context windows. This means the session accumulates context across commands. For long pipeline runs, type `/compact` between major steps if the context grows unwieldy.

### Agents (`@agent-name`)

Agents are markdown files in `.opencode/agents/`. When you type `@refiner` in chat (or when a command invokes one), OpenCode routes the conversation to that agent's system prompt. The agent reads its instructions and responds.

**Key difference from Claude Code:** In Claude Code, each `Agent` tool call runs in an isolated context window. In OpenCode, `@agent-name` delegation happens within the current session — the agent sees the conversation history up to that point. This means:
- Agents inherit context from earlier in the conversation (useful: they see the wiki content you already discussed).
- Long pipeline runs accumulate context (trade-off: use `/compact` at gate pauses if needed).

### Summary of syntax

| What you want | OpenCode syntax |
|---|---|
| Run a command | `/command-name [optional argument]` |
| Invoke an agent | `@agent-name [your message]` |
| Run a skill script | `/skill-name` (which runs the Python script) |
| Ask a general question | Just type normally |

---

## 4. The full pipeline flow: building a new feature

This is the main loop. Use it for any behavioral change — a new API endpoint, a new UI component, anything that needs a test.

You have two ways to drive it:

- **Manual** — invoke each step yourself. Full control, inspect output at each step.
- **Auto** — type `/run-pipeline` once. It chains all steps and pauses only at the two human gates.

The steps are identical either way.

---

### Step 1 — Refine requirements

```
/refine-requirements
```

or, if using auto:

```
/run-pipeline
```

The `@refiner` agent does three things:

1. **Reads the wiki** (`OVERVIEW.md`, `DATA_MODELS.md`, `API.md`, `ARCH_DECISIONS.md`) for context.
2. **Asks 3–5 clarifying questions** in a single batched message. Answer all of them at once.
3. **Runs impact analysis** — searches the codebase for every symbol the change touches, identifies consumers and side-effect surfaces, rates breakage risk per consumer. On a new project with few files this is fast. As the project grows this becomes the step that saves you from missed side effects.

**Output:** `.github/requirements/requirements.md` (or a `requirements-index.md` + sub-files for large changes).

**What good output looks like:**

```markdown
# Requirement: Add user registration endpoint

## Problem
The app has no way to create new users. We need a POST /users endpoint
that accepts email and password, validates them, and returns a user object.

## In Scope
- POST /users endpoint
- Email format validation
- Password hashing (bcrypt)
- Unique email constraint

## Out of Scope
- Email verification flow
- OAuth

## Impact Analysis
**Symbols / modules the change touches:**
- `UserRepository` — does not exist — will be created
...
```

> **Tip:** The refiner will ask about edge cases you haven't thought of. Answer honestly — "I don't know yet" is a valid answer and it becomes an Open Question. The spec-critic will flag if critical unknowns are unaddressed.

---

### Step 2 — Gate 1: Spec Critic

```
@spec-critic
```

(Skip this if using `/run-pipeline` — it runs automatically.)

The spec critic reads the requirements against the wiki and returns a **binary** verdict. It checks nine things: feasibility against your data model, architecture constraints, banned dependencies, edge case coverage, testability, circularity, scope coherence, impact analysis depth, and decomposition compliance.

**If APPROVED:** The critic says `### SPEC CRITIC VERDICT: APPROVED`. When running manually, review the spec and type `approve` to continue to planning. When running `/run-pipeline`, it pauses here for your approval.

**If REJECTED:** The critic names the one concrete change that unblocks the spec. Fix `requirements.md` and re-run `@spec-critic`. Common rejections on a new project:
- "Wiki DATA_MODELS.md is empty" → fill it in first.
- "Edge case X (e.g. duplicate email) is not addressed" → add an acceptance criterion.
- "Acceptance criterion is not observable" → rewrite it as Given/When/Then.

> **Note for new projects:** On your very first cycle, `@spec-critic` may reject because `DATA_MODELS.md` is empty. That is correct — fill it in and re-run. Don't override this check; filling the wiki correctly pays off from the second cycle onward.

---

### Step 3 — Plan

```
/create-implementation-plan
```

The `@planner` agent reads the approved spec, the full wiki (all seven files), and the codebase. It produces `.github/implementation-plan.md` with:

- **Files to Change** — every file that needs to be created, modified, or deleted.
- **Test Plan** — one test case per acceptance criterion.
- **Implementation Steps** — numbered, atomic. Not "implement the endpoint" — "Add `UserRepository.create(email, passwordHash): Promise<User>`".
- **Wiki Updates Required** — what `@scribe` must update after this lands.

Every high-risk consumer from the impact analysis must appear in `Files to Change` or be explicitly justified as "no change needed."

---

### Step 4 — Implement

```
/implement-plan
```

This follows the **11-step YAML rail**, hard-blocking on failure at every step:

| Step | What happens | Blocks on |
|---|---|---|
| 1. read_plan | Reads and confirms understanding of the plan | Unclear or missing plan |
| 2. read_wiki_patterns | Reads PATTERNS.md, extracts conventions | Empty PATTERNS.md |
| 3. **write_tests_first** | Writes failing tests (TDD red phase) | Tests not actually failing |
| 4. write_code | Implements just enough to pass tests | Cannot pass without unauthorized scope |
| 5. **lint** | Runs project linter, fixes all errors | Any lint error remaining |
| 6. **type_check** | Runs tsc/mypy, fixes all errors | Any type error remaining |
| 7. **unit_tests** | Runs full test suite | Any test failing |
| 8. explain_test_changes | Documents reason for any modified existing test | Modified test with no documented reason |
| 9. complexity_check | Runs `/code-analyzer` on changed files | (warns, does not block) |
| 10. wiki_pattern_check | Re-verifies naming/DI against PATTERNS.md | Pattern deviation |
| 11. submit | Emits IMPLEMENTER REPORT | — |

**When a step blocks:** The implementer posts the error verbatim and stops. Fix the underlying issue and re-invoke `/implement-plan` — the checkpoint file (`.github/implementation-progress.json`) resumes from the blocked step, skipping already-done steps.

**Scope expansion:** If the implementer discovers a file outside `Files to Change` that must be modified (e.g., the impact analysis missed a consumer), it stops and emits a `### SCOPE EXPANSION REQUEST` block. You can:
- Type `approved` to approve inline.
- Add a `pipeline-overrides.yaml` entry if running autonomously.
- Type `decline` to kick back to the planner to revise.

---

### Step 5 — Gate 2: Pattern Critic

```
@pattern-critic
```

(Skip if using `/run-pipeline`.)

The pattern critic reads the diff against `.wiki/PATTERNS.md`, `DEPENDENCIES.md`, and `API.md`. It also runs `/code-analyzer` on changed files and physically inspects the diff for test files (not just the implementer's self-report).

Ten checks: plan adherence, wiki patterns, dependencies, API contracts, complexity, tests, YAML rail completeness, dead code/TODOs, lint suppression, and test change justification.

**If APPROVED:** Review the diff and type `approve`. The verdict may include complexity `Flags` — warnings that aren't blocking but you should acknowledge.

**If REJECTED:** Do not re-run `/implement-plan` from scratch. Instead:

```
/fix-rejection
```

This reads the rejection log, shows you exactly what it will change, waits for your `confirm`, applies only those fixes, re-runs lint/type_check/unit_tests/explain_test_changes/complexity_check/wiki_pattern_check, and resubmits to `@pattern-critic`.

---

### Step 6 — MR Description (optional)

```
/create-mr-description
```

Reads `requirements.md`, `implementation-plan.md`, and the git diff, then produces a structured MR description ready to paste into your PR: What / Why / Changes / Tests / Acceptance Criteria / Risks / Notes for Reviewer. Run this after Gate 2 approval if you want a pre-written PR description.

---

### Step 7 — Scribe

```
@scribe
```

The scribe reads the `Wiki Updates Required` section from the plan and appends entries to the listed `.wiki/` files. It is the **only** agent that writes to `.wiki/`. One user-facing line goes into `CHANGELOG.md`.

After scribe runs, the pipeline is complete. Commit and open your PR.

---

## 5. The two human sync points

You approve exactly twice per successful cycle:

| Gate | When | What you're deciding |
|---|---|---|
| **Gate 1 — Sync** | After Spec Critic APPROVED | Does this spec describe what I actually want to build? |
| **Gate 2 — Sync** | After Pattern Critic APPROVED | Is this diff the change I want to merge? |

On any critic rejection you also decide: fix it or abandon?

When running `/run-pipeline`, these are the only points where it pauses for you.

---

## 6. Context management in OpenCode

Unlike Claude Code, OpenCode agents don't run in isolated context windows. Everything runs in the same session. For a short pipeline cycle (one small feature) this is fine — the total context stays manageable. For longer runs:

**Use `/compact` at gate pauses.** Before typing `approve` at Gate 1 or Gate 2, type:

```
/compact
```

This summarizes the conversation so far, keeping the key facts (spec content, plan content, handoff blocks) while reducing the raw token count. The pipeline can then continue cleanly.

**For requirements-index runs (multi-sub-cycle),** use `/compact` between sub-cycles:

```
# After sub-cycle 1 scribe completes:
/compact
# Then proceed to sub-cycle 2
```

**What gets lost on compaction:** Raw message history. What's preserved: any files written to disk (`.github/requirements/`, `.github/implementation-plan.md`, `.github/rejection-log.md`, `.wiki/`). Because the pipeline uses files as handoff artifacts rather than passing content through chat history, compaction is safe at any gate pause.

---

## 7. Building a new app from scratch: the first three cycles

Here's what a realistic first day with a new app looks like.

### Cycle 0 (setup, not a feature)

```
/wiki-init
```

Then edit `.wiki/OVERVIEW.md`, `.wiki/DEPENDENCIES.md`, `.wiki/PATTERNS.md`, and `.wiki/DATA_MODELS.md` by hand. Commit.

### Cycle 1: First feature (e.g. user model + repository)

Start the pipeline:
```
/run-pipeline
```

When asked "Describe the change you want to make":
> "I need a User model and a UserRepository with methods for creating users and finding them by email."

The refiner will ask about:
- What fields does a User have?
- What database / ORM are you using?
- What should happen on duplicate email?
- What is the expected return type?
- Any password hashing requirements?

Answer these, then let the pipeline run. At Gate 1, review the spec carefully — this is the first spec, so the impact analysis section may be thin (the codebase is empty). That's fine; approve it. At Gate 2, review the diff: you should see a model file, a repository file, and test files for each.

### Cycle 2: Second feature (builds on Cycle 1)

By now `.wiki/` has been updated by scribe with the User schema and repository patterns. When the refiner runs impact analysis on the next feature (e.g. an authentication endpoint), it will find `UserRepository` as a consumer and rate it accordingly. The wiki is doing its job.

### Cycle 3+: Patterns harden

After 2–3 cycles, `@pattern-critic` starts being useful — it enforces the naming, DI, and test conventions scribe has recorded. At this point the system is self-reinforcing: each cycle's output becomes the next cycle's constraints.

---

## 8. Using components on their own

You don't have to run the full pipeline every time.

### Agents alone

| Agent | Use on its own when… |
|---|---|
| `@refiner` | You have a vague idea and want a testable spec before committing to implementation. |
| `@planner` | You already have a spec (yours or hand-written) and want a concrete implementation plan. |
| `@spec-critic` | Second opinion on a spec. Works on specs you wrote manually, not just ones from the refiner. |
| `@pattern-critic` | Run on any diff — even one not produced by `/implement-plan` — to check for pattern violations, banned deps, or missing tests. |
| `@scribe` | You made a change manually and want the wiki updated. Hand it the diff and the plan's `Wiki Updates Required` list. |

### Commands alone

| Command | Use on its own when… |
|---|---|
| `/refine-requirements` | Identical to invoking `@refiner` directly. |
| `/create-implementation-plan` | You have an approved spec and want a plan without running Gate 1 again. |
| `/implement-plan` | You have a plan and want code written under the TDD rail. |
| `/fix-rejection` | After any Gate 2 rejection — always prefer this over re-running `/implement-plan` from scratch. |
| `/write-tests` | You want tests written for an existing file, outside of a pipeline cycle. |
| `/explain-changes` | Ask "why was X changed?" — traces the answer back to `requirements.md` and `implementation-plan.md`. |
| `/create-mr-description` | Generate a structured PR description from the pipeline artifacts. |

---

## 9. Composition patterns

**"I want a spec and a plan, but I'll write the code myself."**
```
/refine-requirements → @spec-critic → /create-implementation-plan
```
Stop after planning. Implement by hand. Run `@pattern-critic` on your diff when done.

**"I have existing code I want reviewed against our patterns."**
```
@pattern-critic
```
Paste or describe the diff. No spec or plan required.

**"I want to understand how a feature works."**
```
/llm-wiki
```
Builds a context document from `.wiki/` + source files. Then ask your question.

**"I'm adding a banned library for a one-time exception."**
Add an override to `.github/pipeline-overrides.yaml`:
```yaml
cycle_id: 2025-01-20-import-fix
overrides:
  - critic: pattern-critic
    check: dependencies
    reason: "One-time use of legacy-lib for migration; will be removed in next cycle."
    expires_after_cycles: 1
```
The override is recorded — no silent bypasses.

**"A code review caught a mistake I want to prevent forever."**
Route the finding to the right wiki file:

| Finding | Where to encode it |
|---|---|
| Naming / style / test convention | `.wiki/PATTERNS.md` |
| Wrong library used | `.wiki/DEPENDENCIES.md` (mark as banned) |
| Architectural mistake | `.wiki/ARCH_DECISIONS.md` (add an ADR) |
| Wrong API contract | `.wiki/API.md` |

Then tell `@scribe`:
> "A reviewer flagged that we should never call `UserService` directly from a route handler. Add a `PATTERNS.md` entry prohibiting it."

Once it's in the wiki, `@pattern-critic` enforces it on every future diff automatically.

---

## 10. Pipeline overrides

The override file (`.github/pipeline-overrides.yaml`) replaces the practice of commenting out critic checks. Every bypass is declared and recorded.

**Common uses:**

**Start mid-pipeline** (you already have a hand-written plan):
```yaml
cycle_id: my-feature
entry_point:
  start_at: implement
```

**Override a specific check** (the check genuinely doesn't apply):
```yaml
cycle_id: my-feature
overrides:
  - critic: spec-critic
    check: edge-cases
    reason: "Removing a dead code path; no edge cases to cover."
    expires_after_cycles: 1
```

**Run fully autonomously** (no gate pauses, all overrides pre-declared):
```yaml
cycle_id: my-feature
entry_point:
  pauses: none
overrides:
  - critic: spec-critic
    check: edge-cases
    reason: "Trivial rename — no behavioral change."
    expires_after_cycles: 1
```

The `cycle_id` must match the current cycle. A file with a stale `cycle_id` is ignored (you'll see a warning). This prevents overrides from accidentally persisting across cycles.

---

## 11. Decomposition: when one requirement becomes many

If `@refiner`'s impact analysis shows any of these, it automatically splits the requirement:

- More than 5 files with non-trivial changes
- More than 2 architectural boundaries crossed
- Introduces a new pattern (new DI style, new state management, new error handling)
- Modifies a shared API consumed by more than 3 call sites

You'll get a `requirements-index.md` plus individual sub-files instead of a single `requirements.md`. Each sub-requirement runs its own full pipeline cycle. `/run-pipeline` walks them in dependency order.

This matters more as the project grows. For early cycles on a new app, most features won't trigger decomposition.

---

## 12. Troubleshooting

**"@spec-critic rejects with 'wiki is empty'."**
Fill in `.wiki/DEPENDENCIES.md` and `.wiki/DATA_MODELS.md`. These are required for the critic to function. `/wiki-init` creates the files; you need to add content.

**"@pattern-critic rejects everything — PATTERNS.md is empty."**
On a new project, populate `PATTERNS.md` with your intended conventions by hand. After the first cycle, `@scribe` will take over. If you're mid-pipeline, add the minimal patterns now and re-run `@pattern-critic`.

**"@pattern-critic rejects a naming convention I changed my mind about."**
The critic only enforces what's in the wiki. Edit `.wiki/PATTERNS.md` to reflect the new convention. Run `@pattern-critic` again.

**"/implement-plan blocked at lint / type_check / unit_tests."**
This is working as intended. Read the verbatim error output. Fix the issue. Re-run `/implement-plan` — it resumes from the blocked step via the checkpoint file. You do not need to restart from step 1.

**"I want to restart /implement-plan from scratch."**
Delete `.github/implementation-progress.json`. The next run starts from step 1.

**"@pattern-critic rejected my diff. Do I re-run /implement-plan?"**
No. Run `/fix-rejection`. It reads the rejection log, applies only the required fixes, re-runs the downstream verification steps, and resubmits. Re-running `/implement-plan` from scratch re-does all 11 steps unnecessarily.

**"The pipeline is slow / context feels full."**
Type `/compact` at any gate pause. The key artifacts (spec, plan, wiki files) are all on disk — compacting the chat history doesn't lose anything important.

**"I invoked @refiner but it asked questions I already answered earlier in the session."**
This happens when the agent context window is full or has been compacted. Briefly re-state the key context: "We're building a task management API, PostgreSQL, the user model already exists at `src/models/user.py`." The agent will pick it up.

**"OpenCode says it can't find my agent / command."**
Verify the file is in `.opencode/agents/` or `.opencode/commands/` (relative to the project root, not `~/.config/opencode`). OpenCode looks in the project directory first. Check that the frontmatter has a valid `name:` field.

**"I'm getting a different model than expected."**
OpenCode reads `opencode.json` for the default model. Per-agent model overrides are in each agent's frontmatter (`model: anthropic/claude-opus-4-6`). If the model name is wrong, OpenCode falls back to the default. Check the exact model ID at https://opencode.ai/docs/models.

**"The rejection log shows the same root cause repeatedly."**
This means a gap in the wiki — a constraint the critics are enforcing correctly but that keeps catching you off-guard. Add the constraint to the appropriate wiki file. Once it's documented, you'll write specs that pass it the first time.

---

## 13. Rejection log (`.github/rejection-log.md`)

Every critic rejection is appended here automatically. It is append-only — entries are never modified.

**Sample entry:**
```
**Timestamp:** 2025-06-01T10:22:00Z
**Critic:** spec-critic
**Cycle:** 2025-06-01
**Rejection reason:** The spec requires a `role` field on User but DATA_MODELS.md has no such field. Update the data model before this spec can be evaluated.

**Required fixes:**
- Add `role: enum(admin, member)` to the User model in DATA_MODELS.md.
```

**How to use it:** When a cycle keeps failing, read the log. Multiple entries with the same root cause point to a structural gap in the wiki. Hand the log to `@scribe` before a release to produce a rejection-pattern summary in `CHANGELOG.md`.

---

## 14. When to skip the pipeline

Not every change needs the full pipeline. Skip it for:

- Typo fixes
- Variable / file renames with no semantic change
- Dependency version bumps (unless major-version upgrades)
- Comment-only changes
- Config changes with no code impact

**Rule of thumb: if the change needs a test, it needs the pipeline.**

For a skip: edit the code, run tests, commit. `@scribe` doesn't need to update the wiki unless something architectural changed.

---

## 15. What this system does not do

- No automatic production verification — that belongs in CI/CD.
- No automatic PR creation — `/create-mr-description` writes the description; you open the PR.
- No cross-repo orchestration.
- No enforcement of anything not written in `.wiki/` — the critics are only as good as the wiki they read.
