---
description: Run the full RPI pipeline from idea to wiki update. Supports partial entry points, declared overrides, autonomous agent handoffs, and walking a requirements-index across sub-cycles.
---

# TASK: Pipeline Orchestrator

You are running the SemiPilot Pro pipeline as a real orchestrator — you invoke agents by name using `@agent-name` and route between them based on `### HANDOFF:` blocks in their reports. You pause only at the configured human sync gates. Your job is coordination, not judgment.

Take a deep breath and work through this step by step.

---

# PRE-FLIGHT

## 1. Read pipeline overrides

Check for `.github/pipeline-overrides.yaml`. If it exists:

- Validate the `cycle_id` field matches the current cycle. If absent or mismatched, treat the file as ignored and warn Dev once.
- Read `entry_point.start_at` (default: `refine`).
- Read `entry_point.inline_inputs` for any artifacts provided directly.
- Pass any `overrides:` entries through unchanged to the critics — they apply them.

## 2. Determine entry point

`start_at` ∈ `{refine, spec-critic, plan, implement, pattern-critic, scribe}`. Validate the required inputs per `AGENTS.md > Partial Entry Points`:

- If starting past `refine` without `requirements.md` or `inline_inputs.requirements` → stop and report what's missing.
- If starting past `plan` without `implementation-plan.md` or `inline_inputs.plan` → stop and report.
- If starting at `pattern-critic` or `scribe`, confirm the working tree has a diff to evaluate.

If any inline input is provided, write it to the standard path before proceeding (e.g., `inline_inputs.plan` → `.github/implementation-plan.md`).

## 3. Determine pause configuration

Read `entry_point.pauses` (optional). Defaults to pausing after Gate 1 and Gate 2. Other values:

- `none` — autonomous; do not pause. Used when overrides handle every potential rejection.
- `after-each-step` — pause for Dev acknowledgement after every agent.
- `at-gates` (default) — pause only after spec-critic APPROVED and pattern-critic APPROVED.

## 4. Decomposed input?

Check if the requirements artifact is `requirements-index.md`. If so, this run walks N sub-cycles in dependency order. Each sub-cycle runs steps 3–7 below. The orchestrator's outer loop handles the index; the inner loop is a normal cycle.

---

# ORCHESTRATION RULES

- **Every agent invocation uses `@agent-name` inline.** Do not paste agent prompts inline — just address the agent by name. Available agents: `@refiner`, `@spec-critic`, `@planner`, `@pattern-critic`, `@scribe`. For implementer and fix-rejection, those are commands not agents — invoke them in-context with `/implement-plan` and `/fix-rejection`.
- **Read each agent's `### HANDOFF:` block** at the end of their report. That is the routing signal. Do not infer the next step from prose.
- **On REJECTED**, route per the verdict's `### HANDOFF:` target (refiner or fix-rejection).
- **On hard block from `/implement-plan`**, surface the blocked-step error verbatim and stop. Wait for Dev to type `resume` (the checkpoint file picks up where it failed) or `abandon`.
- **Never skip a step** unless `start_at` legally placed the cycle past it.

---

# STEP 0 (start_at=refine only): GET THE IDEA

If `start_at` is `refine`, ask Dev once:

> "Describe the change you want to make."

Wait for the reply. Pass it as the user idea to `@refiner`.

---

# STEP 1 (skipped if start_at > refine): REFINE

Invoke `@refiner` with the user idea. The refiner produces either `requirements.md` or `requirements-index.md` + sub-files, including the Impact Analysis section. Read its `### REFINER REPORT` and `### HANDOFF: spec-critic` target.

If `pauses == after-each-step`, pause and wait for Dev acknowledgement.

---

# STEP 2 (skipped if start_at > spec-critic): GATE 1 — SPEC CRITIC

Invoke `@spec-critic`, passing the requirements path the refiner handed off. The critic returns the SPEC CRITIC VERDICT block.

**If REJECTED:**
- The critic has already logged to `rejection-log.md`.
- Post the required fix and ask Dev: "Type **revise** to loop back to refine, or **abandon** to stop. To bypass this check (and record it), add an override entry to `.github/pipeline-overrides.yaml` and re-run."
- On `revise`, loop to STEP 1 with Dev's revision. On `abandon`, stop.

**If APPROVED:**
- If `pauses` includes Gate 1 (default), post the GATE 1 sync block and wait for Dev `approve` or revision. On revision, loop to STEP 1.
- If `pauses == none`, continue immediately.

---

# STEP 3 (skipped if start_at > plan): PLAN

Invoke `@planner` with the approved requirements path. The planner produces `implementation-plan.md` (or per-sub-requirement plans + an index). Read the `### PLANNER REPORT` and HANDOFF.

If `pauses == after-each-step`, pause.

---

# STEP 4 (skipped if start_at > implement): IMPLEMENT

Run `/implement-plan` in-context. It executes the 11-step YAML rail with checkpointing.

**On hard block:**
- Post the blocked step's verbatim error.
- Wait for Dev: `resume` (re-enters the rail; checkpoint file picks up) or `abandon` (stop).

**On `### SCOPE EXPANSION REQUEST` from the implementer:**
- If `pipeline-overrides.yaml` has a matching `check: plan-adherence` entry whose reason matches, auto-approve and continue.
- Otherwise pause and surface the request to Dev. On `approved`, continue. On `decline`, route back to `@planner` to revise the plan.

On completion, the IMPLEMENTER REPORT ends with `### HANDOFF: pattern-critic`. Continue.

---

# STEP 5 (skipped if start_at > pattern-critic): GATE 2 — PATTERN CRITIC

Invoke `@pattern-critic`. The critic returns the PATTERN CRITIC VERDICT block.

**If REJECTED:**
- The critic has already logged to `rejection-log.md`.
- Post the required fix. Ask Dev: "Type **fix** to apply via /fix-rejection, or **abandon**."
- On `fix`, run `/fix-rejection` (it applies the fixes and re-runs downstream rail steps, then emits the FIX REPORT). Loop to STEP 5 with the new diff.

**If APPROVED:**
- If `pauses` includes Gate 2 (default), post the GATE 2 sync block and wait for Dev `approve` or concerns. On concerns, loop to STEP 4.
- If `pauses == none`, continue.

---

# STEP 6 (optional): MR DESCRIPTION

If `entry_point.skip_mr_description: true`, skip. Otherwise ask:

> "Would you like me to generate an MR description? Type **yes** or **skip**."

On `yes`, run `/create-mr-description`. Then continue.

---

# STEP 7 (skipped if start_at > scribe): SCRIBE

Invoke `@scribe` with the approved plan path. The scribe updates `.wiki/` and `CHANGELOG.md`, then returns the SCRIBE REPORT with `### HANDOFF: done`.

---

# STEP 8: INDEX CONTINUATION OR COMPLETION

If this cycle was a sub-cycle from a `requirements-index.md`:
- Mark the sub-cycle complete in `.github/pipeline-overrides.yaml` (or a sibling progress file `.github/index-progress.json`).
- Identify the next sub-requirement whose dependencies are all complete.
- Loop to STEP 3 with that sub-requirement (refine is already done at the index level).
- When all sub-cycles complete, run any `Cross-Cutting Acceptance` criteria from the index, then continue.

Post:

```
### PIPELINE COMPLETE

Cycle summary:
- Entry point: <start_at>
- Requirements: <path(s)>
- Plan: <path(s)>
- Sub-cycles run: <N or "n/a">
- Wiki updated: <list>
- MR description: <generated | skipped>
- Overrides honored: <count>
- Scope expansions: <count>

Next step: open your MR. The diff is ready.
```

---

# HARD CONSTRAINTS

- **Route by HANDOFF blocks, not prose.** If an agent's report has no HANDOFF block, treat the run as malformed and stop.
- **Do not skip Dev sync gates unless `pauses == none` was explicitly set.** Defaults pause at Gate 1 and Gate 2.
- **Do not honor an override file whose `cycle_id` does not match.** Warn and proceed without overrides.
- **Do not collapse a `requirements-index.md` into a single cycle.** Each sub-requirement gets its own full plan → implement → pattern-critic → scribe pass.
- **On ambiguity, pause and ask Dev.** Never auto-proceed past an undefined condition.
- **If Dev goes idle mid-pipeline, wait.** Do not assume approval.
