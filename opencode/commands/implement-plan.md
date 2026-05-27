---
description: Execute an implementation-plan.md by following the YAML rail. TDD, no shortcuts, every step reported.
---

# TASK

You are implementing `.github/implementation-plan.md` by following the **YAML execution rail** below. You may not skip, reorder, or invent steps. You must report each step as you complete it — the pattern critic verifies your report against the rail before approving the diff.

Take a deep breath and work through this step by step.

# PRE-FLIGHT

1. Confirm `.github/implementation-plan.md` exists. If not, stop.
2. Confirm `.wiki/` exists and `PATTERNS.md` is non-empty. If empty, stop: "Wiki patterns not populated. `@scribe` must seed `PATTERNS.md` before implementation."
3. Read the plan in full. Read `.wiki/PATTERNS.md` in full.
4. Execute the checkpoint initialization procedure below before running any YAML step.

# CHECKPOINT MANAGEMENT

## Cycle ID derivation (deterministic)

1. If `implementation-plan.md` has YAML frontmatter with a `cycle_id:` key, use that value verbatim.
2. If the filename is not `implementation-plan.md` (e.g., `2025-01-15-auth-feature-implementation-plan.md`), use the filename stem (e.g., `2025-01-15-auth-feature-implementation-plan`).
3. Otherwise, the `cycle_id` is `implementation-plan`.

If the plan file is always at the default path with no frontmatter `cycle_id:`, the cycle_id is `implementation-plan`. Delete `.github/implementation-progress.json` to force a fresh start when starting a logically new implementation under the same filename.

## Initialization

At the start of every run:

1. Derive the `cycle_id` per the rule above.
2. Check whether `.github/implementation-progress.json` exists.
   - **If it exists and its `cycle_id` matches:** Read the `steps` object. Skip every step whose status is `"done"`. Resume from the first step whose status is `"pending"` or `"failed"`. Report: "Resuming from step `<step_name>`. Steps already done: `<list>`."
   - **If it exists but its `cycle_id` does not match:** Overwrite the file with a fresh record (all steps `"pending"`). Report: "Cycle ID mismatch — starting fresh."
   - **If it does not exist:** Create it with all steps set to `"pending"` and `started_at` set to now.

## Progress file write rules

- After each step **succeeds**: set that step's status to `"done"`, clear `failed_step` and `failure_output`, update `last_updated`.
- After each step **fails** (hard block): set that step's status to `"failed"`, set `failed_step` to the step name, set `failure_output` to the verbatim error, update `last_updated`. Then stop — do not proceed to the next step.
- Write the file atomically after each update (read → modify → write full file).

## Progress file location

`.github/implementation-progress.json` — see `AGENTS.md § Ephemeral Artifacts` for the full schema.

# SCOPE DISCIPLINE

The plan is the boundary. You implement exactly what it specifies — no more, no less.

**Only touch files listed in `Files to Change`.** If making a test pass requires editing a file not in that list, stop and report it. Do not expand scope silently.

**Do not improve code that is not in scope.** If you notice something outside the plan that looks wrong, messy, or improvable — log it as a flag in the IMPLEMENTER REPORT and leave it alone. Do not refactor it, rename it, reformat it, or add a comment about it.

**Do not fix unrelated issues opportunistically.** Lint errors, type errors, or style violations in files the plan does not touch are not your problem in this cycle. If the linter or type checker surfaces an error in an out-of-scope file, stop and report it rather than fixing it.

**Do not add anything the plan is silent about.** No extra logging, no defensive null checks beyond what the tests require, no helper utilities, no convenience methods. If the plan does not mention it, it does not belong in the diff.

If you find yourself touching something the plan does not mention, stop. Either the plan is incomplete (raise a SCOPE EXPANSION REQUEST — see below) or you are drifting out of scope (stop and correct course).

## Scope Expansion Request (when the plan is genuinely incomplete)

If you discover during implementation that a file outside `Files to Change` MUST be modified to satisfy a test or correctly implement the plan — typically because the impact analysis missed a consumer — do not silently expand. Emit a `### SCOPE EXPANSION REQUEST` block at the point of discovery and stop:

```
### SCOPE EXPANSION REQUEST
File: <path>
Reason: <one sentence — cite the impact analysis miss or the discovered side effect>
Plan step affected: <which step requires this>
Auto-approve: false
```

Wait for Dev to either:
- Approve inline (Dev replies "approved"), at which point you proceed and include this block in your IMPLEMENTER REPORT.
- Decline, in which case you stop and report that the plan must be revised (kick back to refiner/planner).
- Approve via `pipeline-overrides.yaml` with a matching `(check: plan-adherence, reason: ...)` entry — used when running autonomously.

Any approved scope expansion appears in the IMPLEMENTER REPORT under `Scope expansions:`. The pattern-critic verifies the block exists and the additions match.

# THE YAML RAIL (execute in order)

## Step 1: read_plan
- Read `.github/implementation-plan.md` completely.
- Confirm you understand every `Implementation Step` and every row of the `Test Plan`.
- Block: if anything is unclear, stop and ask Dev. Do not guess.
- → Checkpoint: mark `read_plan` as `"done"`.

## Step 2: read_wiki_patterns
- Read `.wiki/PATTERNS.md` completely.
- Extract the naming conventions, DI patterns, error-handling patterns, and test conventions you must follow.
- Block: if the file is empty or missing, stop.
- → Checkpoint: mark `read_wiki_patterns` as `"done"`.

## Step 3: write_tests_first
- For every row in the plan's `Test Plan`, write the test file and its assertions **before** any implementation code.
- The tests must fail initially (red phase of TDD).
- Run the test suite and confirm they fail for the right reason (not a syntax error or import error).
- **Block:** if any test passes at this stage when it should be red, stop and investigate — this means the test is not actually exercising new behavior.
- Report: "Tests written: `<list of test file paths>`. All failing as expected."
- → Checkpoint: mark `write_tests_first` as `"done"`.

## Step 4: write_code
- Implement just enough code to make the tests pass.
- Follow the naming and DI patterns from `PATTERNS.md`.
- Do not add scope beyond what the plan authorizes.
- **Block:** if you cannot make a test pass without adding scope the plan did not authorize, stop and report what is blocking rather than expanding scope.
- → Checkpoint: mark `write_code` as `"done"`.

## Step 5: lint
- Detect the linter from `package.json` / `pyproject.toml` / `.eslintrc` / `.flake8` / etc.
- Run the linter. Fix every error. Warnings may remain only if the plan explicitly permits it.
- **Hard block:** if any lint error remains after your fix attempt, stop here. Post the error output. Do not proceed to step 6.
- → Checkpoint: mark `lint` as `"done"` on pass, `"failed"` on hard block (record verbatim error in `failure_output`).

## Step 6: type_check
- If the project is TypeScript, run `tsc --noEmit` (or the equivalent script in `package.json`).
- If the project is Python with mypy, run `mypy <src dir>`.
- Fix every type error. Do not suppress errors with `// @ts-ignore`, `// @ts-expect-error`, `# type: ignore`, or any equivalent suppression comment unless the plan explicitly authorizes it and explains why.
- **Hard block:** if any type error remains after your fix attempt, stop here. Post the full `tsc` / `mypy` output. Do not proceed to step 7.
- If the project has no type checker, note "No type checker detected" and continue.
- → Checkpoint: mark `type_check` as `"done"` on pass (or "no type checker"), `"failed"` on hard block (record verbatim output in `failure_output`).

## Step 7: unit_tests
- Run the full test suite, not just the new tests.
- **Hard block:** if any test fails, stop immediately. Post:
  1. The exact test name(s) that failed.
  2. The failure output verbatim.
  3. Whether the failure is in new test code or pre-existing tests.
  Do not proceed to step 8. Do not attempt a silent fix and re-run without reporting.
- → Checkpoint: mark `unit_tests` as `"done"` on pass, `"failed"` on hard block (record test failure output in `failure_output`).

## Step 8: explain_test_changes
- Examine the diff for every test file (matching `*.test.*`, `*_test.*`, or `*spec*`) that was **modified** (not newly created).
- For each modified test file, produce an entry in this format:
  ```
  Modified test: <path>
  Reason: <why this existing test needed to change — cite the specific implementation step or pattern change that required it>
  ```
- **Block:** if any pre-existing test file was modified and you cannot name a specific reason from the plan or a wiki pattern change, stop and report: "Modified test `<path>` has no documented reason. Explain why this test was changed before proceeding."
- If no pre-existing test files were modified, write: "No existing tests were modified."
- → Checkpoint: mark `explain_test_changes` as `"done"`.

## Step 9: complexity_check
- Run `/code-analyzer` on each file you modified (or `python skills/code-analyzer/run.py <file>`).
- Threshold: no function may exceed cyclomatic complexity 15 unless marked with a `# complexity-exempt: <reason>` comment.
- If a function exceeds 15, refactor it before proceeding — unless the plan explicitly authorizes the complexity.
- File-level complexity increase over 20% → flag for Gate 2 review but do not block.
- Report: complexity results per file.
- → Checkpoint: mark `complexity_check` as `"done"` (this step does not hard-block — always `"done"` regardless of flags).

## Step 10: wiki_pattern_check
- Re-read `.wiki/PATTERNS.md`.
- For each file you changed, verify naming, DI, error handling, and test style match.
- **Block:** on any deviation you cannot justify by citing a specific pattern in the wiki.
- → Checkpoint: mark `wiki_pattern_check` as `"done"`.

## Step 11: submit_for_pattern_critic
- Produce the handoff report (format below).
- → Checkpoint: mark `submit_for_pattern_critic` as `"done"`.
- Stop. Dev invokes `@pattern-critic`.

# REPORTING FORMAT (mandatory)

At the end of every `/implement-plan` invocation, emit this block:

```
### IMPLEMENTER REPORT
Plan: .github/implementation-plan.md

YAML rail execution:
- read_plan: done
- read_wiki_patterns: done
- write_tests_first: done — <N tests written, all initially red>
- write_code: done — <N files modified>
- lint: pass
- type_check: pass | skipped (<reason>) | blocked — <error summary>
- unit_tests: pass — <N/N passing>
- explain_test_changes: <"No existing tests were modified." | list of modified tests with reasons>
- complexity_check: pass | flagged — <per-file summary>
- wiki_pattern_check: pass
- submit_for_pattern_critic: ready

Files changed:
- <path>: <created | modified | deleted>

Scope expansions (if any):
- <path>: <reason — approved by: inline | overrides.yaml> | "none"

Flags (for Gate 2 attention):
- <flag or "none">

### HANDOFF: pattern-critic
target: <plan path>
```

If any step was blocked, replace that step's line with:
```
- <step>: BLOCKED — <what failed> — <what Dev must resolve>
```
Do not fill in any subsequent steps. Stop at the blocked step.

# HARD CONSTRAINTS

- **Do not modify** `.github/requirements/requirements.md` or `.github/implementation-plan.md`. They are inputs.
- **Do not write to `.wiki/`.** That is `@scribe`'s job.
- **Do not skip tests** even if the plan seems obviously correct.
- **Do not add commentary, documentation, or "helper" utilities** the plan did not authorize.
- **Do not mark a step "done" unless it actually passed.** False reports are caught at Gate 2 when the diff contradicts the report.
- **Do not suppress lint, type, or test errors.** Fix them or block and report.
