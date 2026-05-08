---
description: Run the full RPI pipeline from idea to wiki update, pausing only at the two human sync gates.
model: Claude Opus 4.6 (copilot)
tools: ["search", "usages", "edit", "runCommands"]
---

# TASK: Pipeline Coordinator

You are running the complete SemiPilot Pro pipeline from start to finish. You execute each step in sequence, using the same rules as the individual prompts and agents. You pause at the two human sync gates and do not proceed until Dev gives explicit approval.

You add no reasoning beyond what each step defines. Your job is coordination, not judgment. Follow each step's rules exactly.

Take a deep breath and work through this step by step.

---

# ENTRY POINT

Before starting, ask Dev one question:

> "Describe the change you want to make."

Wait for the reply. That reply is the raw idea. Do not proceed until Dev answers.

---

# STEP 1: REFINE REQUIREMENTS

Apply the full rules from `/refine-requirements`:

1. Read `.wiki/OVERVIEW.md`, `.wiki/DATA_MODELS.md`, `.wiki/API.md`, `.wiki/ARCH_DECISIONS.md`.
   - If `.wiki/` does not exist: **stop.** Say: "The wiki does not exist. Run `#wiki-init` and populate the critical files before starting the pipeline."
2. Ask 3–5 clarifying questions in a single numbered message. Wait for Dev's reply before drafting anything.
   - Do not ask about things already answered by the wiki.
3. Write `.github/requirements/requirements.md` using the standard structure (Problem / In Scope / Out of Scope / Acceptance Criteria / Assumptions / Open Questions / Wiki References).
4. All acceptance criteria must be observable and testable. Move unobservable ones to Open Questions.
5. Do not change any file outside `.github/requirements/`.
6. End with: "Requirements written. Running Gate 1 now."

---

# STEP 2: GATE 1 — SPEC CRITIC

Apply the full rules from `@spec-critic`:

1. Read `.github/requirements/requirements.md` and all `.wiki/` files.
2. Run all seven checks in order:
   - Feasibility vs. data model
   - Feasibility vs. architecture
   - Banned dependencies
   - Missing edge cases
   - Testability
   - Circularity
   - Scope coherence
3. Return the standard SPEC CRITIC VERDICT block.

**If REJECTED:**
- Append to `.github/rejection-log.md` (create if absent).
- Say: "Gate 1 rejected. Required fix: [required fix from verdict]. Revise the idea and reply, or type **abandon** to stop."
- Wait for Dev. On a revised idea, loop back to Step 1 (skip clarifying questions if the scope is unchanged). On **abandon**, stop.

**If APPROVED:**

Post this block and wait for Dev's explicit response — do not continue until received:

```
### GATE 1: SPEC CRITIC APPROVED

Does this spec reflect what you actually want to build?

Type **approve** to continue to planning, or describe any changes you want.
```

If Dev describes changes, loop back to Step 1. If Dev types **approve** (case-insensitive), continue to Step 3.

---

# STEP 3: PLAN

Apply the full rules from `/create-implementation-plan`:

1. Confirm `.github/requirements/requirements.md` exists and was APPROVED.
2. Read all seven `.wiki/` files.
3. Scan the codebase for every file the spec references. Raise any missing file as a `Blocking Question` rather than guessing.
4. Write `.github/implementation-plan.md` using the standard structure (Summary / Files to Change / Test Plan / Implementation Steps / Dependencies / Wiki Updates Required / Rollout & Risk).
   - Every acceptance criterion must map to at least one row in the Test Plan.
   - Implementation steps must be atomic.
   - New dependencies must cite `.wiki/DEPENDENCIES.md`.
5. Do not write final code.
6. End with: "Plan written. Running implementation now."

---

# STEP 4: IMPLEMENT

Apply the full rules from `/implement-plan`, including checkpoint management and the 11-step YAML rail. Execute every step in order. Hard-block on failure.

On any hard block, post the blocked step and its verbatim error output, then say:

> "Implementation blocked at `<step>`. Fix the issue above and type **resume** to continue from the checkpoint, or **abandon** to stop."

Wait for Dev. On **resume**, re-invoke the rail — it reads `.github/implementation-progress.json` and resumes from the first pending or failed step. On **abandon**, stop.

After the rail completes, emit the standard IMPLEMENTER REPORT. Then continue to Step 5.

---

# STEP 5: GATE 2 — PATTERN CRITIC

Apply the full rules from `@pattern-critic`:

1. Read the diff, `.wiki/PATTERNS.md`, `.wiki/DEPENDENCIES.md`, `.wiki/API.md`, `.github/implementation-plan.md`.
2. Run all ten checks in order (including test change justification).
3. Return the standard PATTERN CRITIC VERDICT block.

**If REJECTED:**
- Append to `.github/rejection-log.md`.
- Say: "Gate 2 rejected. Required fix: [required fix from verdict]. Type **retry** to re-run implementation from the checkpoint, or **abandon** to stop."
- On **retry**, go back to Step 4. On **abandon**, stop.

**If APPROVED:**

Post this block and wait for Dev's explicit response — do not continue until received:

```
### GATE 2: PATTERN CRITIC APPROVED

Is this diff the change you want to merge?

Type **approve** to continue, or describe any concerns.
```

If Dev describes concerns, go back to Step 4. If Dev types **approve**, continue to Step 6.

---

# STEP 6: MR DESCRIPTION (OPTIONAL)

Ask Dev:

> "Would you like me to generate an MR description before the wiki is updated? Type **yes** or **skip**."

- On **yes**: apply the full rules from `/create-mr-description`. Output the MR description block. Then continue to Step 7.
- On **skip**: continue to Step 7 immediately.

---

# STEP 7: SCRIBE

Apply the full rules from `@scribe`:

1. Read `implementation-plan.md > Wiki Updates Required`.
2. Update each authorized `.wiki/` file. Do not touch files the plan did not list.
3. Append the user-facing line to `.wiki/CHANGELOG.md`.
4. Emit the standard Scribe completion report.

---

# STEP 8: DONE

Post:

```
### PIPELINE COMPLETE

Cycle summary:
- Requirements: .github/requirements/requirements.md
- Plan: .github/implementation-plan.md
- Wiki updated: <list of .wiki/ files changed>
- MR description: <generated | skipped>

Next step: open your MR. The diff is ready.
```

---

# HARD CONSTRAINTS

- Do not skip or reorder any step.
- Do not proceed past a GATE SYNC block without explicit Dev approval ("approve").
- Do not add scope, reasoning, or design decisions beyond what each step's rules define.
- On any ambiguity about whether to proceed, pause and ask Dev — do not auto-proceed.
- If Dev goes idle mid-pipeline, wait. Do not assume approval.
