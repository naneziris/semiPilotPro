---
description: Apply the pattern-critic's required fixes after a Gate 2 rejection, re-run affected rail steps, and resubmit to @pattern-critic.
model: Claude Sonnet 4.6 (copilot)
tools: ["search", "usages", "edit", "runCommands"]
---

# TASK

You are applying targeted fixes after a `@pattern-critic` REJECTION. You do not re-run the full implementation rail. You read the exact fixes the critic required, apply only those, re-run the downstream verification steps, and resubmit.

Take a deep breath and work through this step by step.

---

# PRE-FLIGHT

1. Confirm `.github/rejection-log.md` exists and has at least one entry. If not, stop: "No rejection found. Run `@pattern-critic` first."
2. Confirm `.github/implementation-plan.md` exists. If not, stop.
3. Read `.github/rejection-log.md` in full. Identify the most recent entry for the current cycle (the last entry in the file).
4. Extract the **Required fixes** from that entry. These are the only changes you are authorized to make.
5. Read `.github/implementation-plan.md` — specifically `Files to Change` — to understand the scope boundary.
6. Read the conventions corpus in full: `.github/copilot-instructions.md` plus the `.github/instructions/*.instructions.md` files whose `applyTo` globs match the files in play.

---

# STEP 1: CONFIRM FIXES

**Invocation mode determines who confirms:**

- **Pipeline-invoked** (`/run-pipeline` stated `invoked_by: run-pipeline`): do NOT wait for Dev. The critic's logged Required fixes are the authorization; the orchestrator's retry budget bounds the loop. Post the FIX PLAN block below for the record, replace its last line with `Applying automatically (pipeline-invoked).`, and proceed directly to STEP 2.
- **Direct invocation** (Dev ran `/fix-rejection` manually): confirm with Dev before touching any file, as below.

Post this block before touching any file:

```
### FIX PLAN

Critic: @pattern-critic
Cycle: <cycle_id from rejection log>
Rejection reason: <verbatim Rejection reason from log entry>

Required fixes:
<numbered list from rejection log>

Files I will touch:
<list the specific files affected by each fix>

Type **confirm** to apply these fixes, or describe any adjustments.
```

**Direct invocation only:** wait for Dev's explicit response. Do not proceed until Dev types **confirm** (case-insensitive) or provides adjusted instructions. Pipeline-invoked runs skip this wait.

---

# STEP 2: APPLY FIXES

Apply only the fixes listed in the FIX PLAN — nothing else.

**Scope discipline is identical to `/implement-plan`:**
- Do not touch files not affected by the required fixes.
- Do not refactor, reformat, or improve adjacent code.
- Do not fix unrelated lint or type issues in out-of-scope files.
- Do not add anything the critic's fix list does not mention.

If applying a fix would require touching a file outside the original `Files to Change` table in the plan, stop and report: "Fix requires modifying `<file>`, which is outside the original plan scope. Confirm this is acceptable before proceeding." This stop applies in BOTH invocation modes — scope is always a human decision; when pipeline-invoked, this surfaces as an escalation."

---

# STEP 3: RE-RUN DOWNSTREAM VERIFICATION

Run these steps in order. Resolve commands from package.json scripts first, falling back to `.github/copilot-instructions.md > Commands`. Self-fix loops and hard blocks work exactly as `/implement-plan` does: max 2 reported fix rounds per step, then block.

## lint
- Run the repo's lint command on every file modified in Step 2.
- **Self-fix loop (max 2 rounds):** fix the errors introduced by the fix; re-run. Report each round. Do not fix pre-existing errors in out-of-scope files.
- **Hard block:** if lint errors remain after 2 rounds, stop and post the verbatim output.

## type_check
- Run the repo's typecheck command on the modified files.
- **Self-fix loop (max 2 rounds):** fix every type error introduced by the fix; re-run. Report each round. Do not suppress.
- **Hard block:** if type errors remain after 2 rounds, stop and post the verbatim output.
- If no type checker resolves, note "No type checker detected" and continue.

## unit_tests
- Run the full test suite with the repo's test command.
- **Self-fix loop (max 2 rounds), same guardrails as the rail:** fix the CODE, never weaken, skip, or delete a test; a pre-existing test whose expectations would have to change is an immediate hard block.
- **Hard block:** if failures remain after 2 rounds, stop immediately. Post:
  1. The exact test name(s) that failed.
  2. The failure output verbatim.
  3. Whether the failure is in new test code or pre-existing tests, and what each fix round attempted.

## explain_test_changes
- Check if any pre-existing test file was modified in Step 2.
- If yes, produce a per-file entry:
  ```
  Modified test: <path>
  Reason: <why this existing test needed to change — cite the specific critic fix that required it>
  ```
- If no pre-existing test files were modified, write: "No existing tests were modified."
- **Hard block:** if a test was modified with no documentable reason.

## complexity_check
- Run `#code-analyzer` on each file modified in Step 2.
- Any function exceeding cyclomatic complexity 15 without a `# complexity-exempt:` comment → refactor before proceeding.
- File-level increase over 20% → flag, do not block.

## conventions_check
- Re-read the matching `.github/instructions/*.instructions.md` files.
- For each file modified in Step 2, confirm naming, DI, error handling, and test style match.
- **Hard block:** on any deviation you cannot justify by citing a specific documented convention or card invariant.

---

# STEP 4: EMIT FIX REPORT AND RESUBMIT

```
### FIX REPORT
Cycle: <cycle_id>
Addresses rejection: <timestamp from rejection log entry>

Fixes applied:
<numbered list matching the Required fixes from Step 1 — one line per fix, with the file and line changed>

Downstream verification:
- lint: pass | pass after <N> fix round(s) | blocked — <error summary>
- type_check: pass | pass after <N> fix round(s) | skipped (<reason>) | blocked — <error summary>
- unit_tests: pass — <N/N passing> | pass after <N> fix round(s) — <N/N passing>
- explain_test_changes: <"No existing tests were modified." | list of modified tests with reasons>
- complexity_check: pass | flagged — <per-file summary>
- conventions_check: pass

Files changed in this fix:
- <path>: <modified | deleted>

Flags (for Gate 2 attention):
- <flag or "none">

Ready for @pattern-critic.
```

If any step was blocked, replace that step's line with:
```
- <step>: BLOCKED — <what failed> — <what Dev must resolve>
```
Do not fill in subsequent steps. Stop at the blocked step.

---

# HARD CONSTRAINTS

- Apply only what the rejection log requires. No other changes.
- Do not re-run write_tests_first or write_code from the full rail — the implementation is complete. You are correcting it, not redoing it.
- Do not modify `.github/requirements/requirements.md` or `.github/implementation-plan.md`.
- Do not write to `docs/cards/`, `docs/decisions.md`, `docs/dependencies.md`, or `docs/CHANGELOG.md`. That is `@scribe`'s job.
- Do not mark any step as passing unless it actually passed.
- Do not suppress lint, type, or test errors. Fix them or block and report.
