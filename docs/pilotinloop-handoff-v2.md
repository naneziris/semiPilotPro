# Handoff v2: PilotInLoop Autonomous Loop for SemiPilotPro

## 0. Purpose and what changed from v1

This document is the design of record for the automation layer on top of the human-in-the-loop SemiPilotPro
pipeline (GitHub Copilot in VS Code, running in DevPod). The implementation in `.github/pilotinloop/` follows it;
where the two disagree, fix the code.

**Changes from v1** (each a design bug or gap found in review, not polish):

| # | v1 problem | v2 rule |
|---|---|---|
| 1 | Retry loop reset the tree before every task retry *and* fed the previous attempt's errors to the next attempt — errors about code that no longer existed. | **Task failures keep the failed diff**; the retry fixes it. The tree is reset only for infra failures, call timeouts, scope violations, diff-cap blocks and final give-up (§4.3, §4.6). |
| 2 | Tests written and locked before any code exist would lock the test-writer's guesses about names and signatures; a wrong guess = task BLOCKED with no way out unattended. | Planner emits `interfaces` per task; the test-writer builds only against them; the orchestrator distinguishes **contract errors** (import/name/signature) from assertion failures and allows **one logged test-fixer pass** per task for the former (§3B.3, §6). |
| 3 | Locked tests for later tasks import modules earlier tasks haven't created; the whole suite fails at collection during T1. | **One test file per task**; the tests check runs only the current task's (+ done tasks') files via `{task_tests}`; the full suite runs once at the end (§5). |
| 4 | Copilot quota exhaustion would be classified transient and back off for 90 min before the breaker tripped. | New failure class **`quota_exhausted` → halt immediately** (§4.6). Preflight prints a request upper bound. |
| 5 | Error signature hashed raw first lines; line numbers/paths change between attempts so the stuck detector rarely fires. | Signature strips numbers, paths and addresses before hashing (§6). |
| 6 | Ambiguities: may the implementer add tests? does the test commit count toward the diff cap? dirty tree / existing branch at start? | Implementer may **add** test files, never modify locked ones; diff caps count implementer diffs only; dirty tree or existing branch → refuse to start (§6). |
| 7 | Token/cost budget "if measurable". | Cut. Not measurable via the CLI; iteration + wall-clock caps bound cost. |
| 8 | `plan.json` location left to the prompt ("never pass plan.json"). | `plan.json` lives **outside the repo**; Copilot CLI path verification makes it unreadable without `--add-dir` (§4.3). |
| 9 | Critique loop could accept an un-critiqued re-plan on the last round. | Each planner output is critiqued; after `max_critique_rounds` rejections the run halts `plan_rejected` (§3B.2). Expect a higher halt rate than with a human nodding plans through; that is the point. |
| 10 | Acceptance criteria "must be machine-checkable" with no way to enforce it. | Every criterion carries a `[check: <ref>]` tag; preflight rejects untagged ones; the planner may only reference tagged refs; plan validation checks coverage both ways (§5). |
| 11 | Implementation-progress and decisions got reset with the tree, or polluted task commits. | Orchestrator-managed paths are preserved across resets, excluded from task commits and committed in a separate `[pilotinloop] state:` commit at halt, so the tree is clean and task commits are pure code (§8). |

Everything not listed is unchanged from v1 in substance.

## 1. Context

- Pipeline today: **refine → plan → implement**, human at every step. Agents: refiner, planner, spec-critic,
  pattern-critic, scribe. YAML execution rail with human gates. `.wiki/` knowledge layer (read-only here, §13).
- This work absorbs the previously planned `.github/rejection-log.md` and `.github/implementation-progress.json`.

## 2. Core principle (decided)

> Keep the human at the **front** and the **back**. Remove the human from the **middle**.

Better models don't fix missing information; wrong assumptions at the requirements level compound into a large,
coherent, wrong diff. Implementation-level mistakes are cheap and self-correct in a loop. Human time goes to
intent; machines take the rest. Limited feedback loops stay for requirements and are dropped for execution.

## 3. Target workflow

### Phase A: Pre-flight (interactive, ~10–15 min) — `make preflight FEATURE=<slug>`

1. Run the **refiner** interactively → `requirements.md`.
2. `requirements.md` has an `## Acceptance criteria` section; every bullet ends with `[check: <ref>]` where
   `<ref>` is a test name/substring or a check name (`lint`, `typecheck`, `build`). Preflight fails on any
   untagged criterion.
3. Preflight refuses a dirty tree or an existing `pilotinloop/<slug>-<date>` branch.
4. Health: trivial Copilot CLI call; optional `gh auth status`; optional token-expiry env var vs wall-clock
   budget; prints an upper bound on Copilot requests for the run.
5. Planner runs in **questions-only mode** → `open-questions.md`. No plan is produced.
6. Human answers inline, merges answers into `requirements.md`, commits.
7. `nohup make pilotinloop FEATURE=<slug> &`

### Phase B: PilotInLoop (autonomous) — `make pilotinloop`

1. **Plan**: planner produces `plan.json` (§4.4) to stdout; orchestrator validates (schema, sizing, coverage,
   cycles). Invalid → re-prompt once with the errors, then halt `plan_rejected`.
2. **Critique**: spec-critic and pattern-critic each return `{"verdict", "issues"}`. Any reject → issues
   appended to `.github/rejection-log.md` and fed to a re-plan. After `max_critique_rounds` (default 2)
   rejected rounds → halt `plan_rejected`.
3. **Tests first**: test-writer turns criteria into tests, **one file per task**, built only against the plan's
   `interfaces`. Non-test files it touched are reverted. Test files are checksum-**locked** and committed
   (`[pilotinloop] tests: locked acceptance tests`).
4. **Implement loop** (§4.3): per task in topological order, fresh Copilot CLI process per attempt.
5. **Final full-suite checks** once all tasks are done (interactions per-task runs can't see).
6. **Report** (§9) and a `[pilotinloop] state:` commit.

### Phase C: Morning review — read `decisions.md` first

1. Assumptions (from `decisions.md`) are section 1 of the report. Read them before the diff.
2. Wrong assumption → `make rollback TASK=<id>` reverts that task's commit and its dependents (newest first)
   and sets them to `pending`.
3. `make resume` continues from the first non-done task on the same branch.

## 4. Architecture

### 4.1 The orchestrator owns the loop

`orchestrator.py` drives every iteration and runs every check. The agent never decides that work is done.
Done = all configured checks pass. Config is YAML (`config.yaml`).

### 4.2 Agent runner (Copilot CLI, verified)

Findings in `docs/copilot-cli-findings.md`. Summary: `copilot -p <prompt> -s --no-ask-user` is a fresh,
non-interactive session that exits when done; `--agent`, `--model`, `--allow-tool`/`--deny-tool` (deny wins),
`--log-dir`, `--share=PATH` are available. Exit codes and error strings for 5xx/429/401/quota are **not
documented**: classification is config-driven regex and must be tuned after the first real dry run.

Interface: `CopilotRunner.run(role, prompt, attempt_label) -> CallResult` (`runner.py`).

### 4.3 One task per Copilot CLI invocation (hard requirement)

A "task" is a planner task (T1, T2, ...), not the refined request. One feature = one run = many tasks.

1. **Structured plan** validated against `plan.schema.json` + sizing rules.
2. **Fresh process per call.** The runner refuses to build a command line containing `--resume`, `--continue`,
   `--session-id` or `-r` (hard-coded + `runner.forbidden_flags`). Tested.
3. **Narrow prompt.** The implementer receives only: the task object, `requirements.md` and `decisions.md`
   (by path), its `expected_files`, the locked test list, and on retry the previous attempt's check errors.
   `plan.json` is stored outside the repo (`state_dir`), where Copilot CLI's path verification blocks reads.
4. **Explicit instruction** (`prompts/implementer.md`): implement only task `<id>`; don't run the full suite or
   decide completion; don't touch git; stop when done; assumptions protocol (§7).
5. **The orchestrator runs checks.** After the CLI exits, in order: timeout → test-lock → scope → per-task
   diff cap → checks. Failure → new invocation for the same task with the errors attached **and the failed
   diff still in the tree**.
6. **Scope enforcement.** `git diff --name-only` + untracked vs `expected_files`. New test files are allowed.
   Extra non-test files within tolerance (default 2) → warning. Beyond tolerance, or touching another task's
   `expected_files` → revert, count as failed attempt; second violation → BLOCKED.
7. **Timeout per call** (default 20 min) → tree reset, failed attempt.
8. **Logging**: prompt, stdout/stderr, exit code, duration, classification →
   `.github/pilotinloop/runs/<run_id>/<label>.log` (untracked via `.git/info/exclude`).

Reference loop (implemented in `PilotInLoop.run_task`):

```python
for task in topo_sort(plan.tasks):
    if any dependency not done: mark(task, blocked); continue
    if budget exhausted: stop
    base = last_good_commit(); seen = set(); errors = None
    while attempts < MAX_RETRIES:
        attempts += 1
        res = runner.run("implementer", prompt(task, errors))       # fresh process; infra retries happen inside
        if res.timed_out:            reset_tree(); errors = "timed out"; continue
        if locked tests modified:    restore those files; errors = "..."; continue          # attempt consumed
        if scope violated:           reset_tree(); errors = "..."; (2nd time → blocked); continue
        if diff > per-task cap:      reset_tree(); blocked; break
        ok, errors = run_checks(task_tests=task_tests(task))
        if ok:                       commit(task); done; break
        if contract_error(errors) and fixes < 1:  test_fixer(); re-run checks; if ok: commit; done; break
        if signature(errors) in seen: break       # stuck
        seen.add(signature(errors))               # keep the diff; next attempt fixes it
    if not done: reset_tree(); mark(task, blocked, summarize(errors))
    save_checkpoint()
```

### 4.4 Plan schema and task sizing

`plan.json` per `plan.schema.json`; `interfaces` (exact module paths, names, signatures the task creates or
relies on) is the contract the test-writer and dependent tasks build against. Sizing rules (schema + validator
+ pattern-critic): ≤ 5 `expected_files` (configurable); size `S|M` only; every task maps to ≥ 1 tagged
criterion; every tagged criterion is covered by ≥ 1 task; no cycles; only refs that exist in `requirements.md`.

### 4.5 Sandbox

DevPod container. Runs happen on `pilotinloop/<feature-slug>-<date>` created at run start. Never push.

### 4.6 Infrastructure failure handling

Infra failures and task failures never share a budget.

| Class | Detection (config regex) | Action |
|---|---|---|
| Transient | 502/503/504, 429, connection reset/refused, DNS, timeout text | Reset tree, backoff with jitter (1→2→4→8→16 min, cap 15), retry the **same call**; the task attempt counter does not move. Honour `retry-after` if present. |
| Fatal | 401/403, expired/invalid token, no subscription/entitlement | Halt immediately: `auth_failure`. |
| **Quota exhausted** | quota / credit limit / session limit / premium request text | Halt immediately: `quota_exhausted`. Never backoff — waiting doesn't refill it. |
| Unknown | unrecognised non-zero exit | Transient once; if it repeats, task failure; raw output kept for pattern updates. |
| Task failure | CLI exited 0 but checks/scope/lock failed; or call timeout | Task retry logic (§4.3). |

Circuit breaker: continuous outage > `max_outage_seconds` (90 min) or total > `max_total_outage_seconds`
(150 min) → reset tree, interrupted task back to `pending` with its attempt refunded, halt `copilot_unavailable`.
Optional `retry_window` ("05:00") schedules one automatic resume. `resume` retries pending tasks normally.

Preflight is the only point where a human can still fix auth: an expired token at 1 am is likelier than an outage.

## 5. Definition of done

- Every acceptance criterion is tagged `[check: <ref>]` and covered by a task.
- A task is done when all configured checks pass. The tests check receives `{task_tests}` = locked test files
  mentioning this task's refs (and done tasks' refs) + any new test files; lint/typecheck/build run globally.
- After the last task, the full suite runs once; a failure is a loud warning in the report (tasks stay done —
  the human decides).
- The run is complete when all tasks are done or blocked, or a budget is hit.

## 6. Guardrails (all implemented, all in `config.yaml`)

| Guardrail | Rule | Default |
|---|---|---|
| Retries per task | implement→check attempts | 3 (effectively 2 if the same error repeats — see stuck detection) |
| Total iterations | implementer calls per run | 30 |
| Wall-clock | hard stop | 6 h |
| Critique rounds | plan-critique cycles before `plan_rejected` | 2 |
| Stuck detection | same normalised error signature twice → BLOCKED | on; signature = failing test names + first error line with numbers/paths/hex stripped, sha1 |
| Test lock | checksum of locked files after every implementer call; modified → restore those files, failed attempt. Implementer **may add** new test files. | on |
| Contract fix | locked test fails with import/name/signature error → one test-fixer call, names/imports only, logged as a REVIEW warning; re-lock | 1 per task |
| Branch safety | run branch only; `git push`, `git reset`, `git clean`, `git checkout`, `git branch` denied to the agent | on |
| Command deny-list | `--deny-tool` on every call: push, clean, reset, rm, sudo, publish, installs, docker/kubectl/terraform, curl/wget, url, memory | configurable |
| Diff size cap | implementer diff per task / sum per run (locked-test commit excluded) | 400 / 3000 lines |
| Dependency halt | dependents of a BLOCKED task are BLOCKED | on |
| One task per call | fresh process; forbidden flags refused; plan outside repo | on |
| Scope check | extra non-test files tolerance; another task's files → violation | 2 |
| Call timeout | kill the CLI; failed attempt; tree reset | 20 min |
| Task size | max `expected_files` | 5 |
| Infra retries | transient backoff, never against task retries | 1→16 min, cap 15 |
| Outage breaker | continuous / total | 90 / 150 min |
| Auth / quota | halt immediately | on |
| Clean start | dirty tree or existing run branch → refuse | on |

## 7. Assumptions protocol

Injected into the implementer and test-writer prompts:

> When you hit ambiguity not resolved by `requirements.md` or `open-questions.md`, do exactly one of:
> 1. choose the **most reversible** option and log it in `decisions.md` (format below), or
> 2. stop and print `BLOCKED: <the question you would ask>`.
> You must never guess silently.

```
## D-<n> — <short title>
- Task: <task id>
- Ambiguity: <what was unclear>
- Chosen: <option taken>
- Alternatives: <what else was possible>
- Reversibility: <how to undo; which files>
```

## 8. Checkpointing & resumability

- Commit after every completed task: `[pilotinloop] <task-id>: <title>` — code only.
- Orchestrator-managed paths (`decisions.md`, `.github/implementation-progress.json`,
  `.github/rejection-log.md`, `reports/`) are preserved across tree resets, excluded from task commits and
  committed together as `[pilotinloop] state: <stop_reason>` when the run halts. Task commits are therefore
  pure and `rollback` reverts cleanly.
- `.github/implementation-progress.json` tracks run id, branch, base commit, per-task status/attempts/commit/
  blocked reason/contract fixes/diff stats, budget, infra summary, test-lock checksums, critique verdicts,
  warnings, stop reason.
- `resume`: checks out the run branch, resets any dirty state, sets `in_progress` → `pending`, continues.
- `rollback <task-id>`: `git revert` the task and its dependents newest-first; statuses → `pending`.

## 9. Morning report — `reports/pilotinloop-<date>-<feature>.md`

1. Assumptions (`decisions.md`) — first.
2. Blocked tasks with the reason / question.
3. Completed tasks with commit SHAs (+ pending ones if interrupted).
4. Check results (final full suite if reached).
5. Diff stats per task.
6. Budget: iterations, wall-clock, stop reason (`completed`, `budget_exhausted`, `copilot_unavailable`,
   `auth_failure`, `quota_exhausted`, `plan_rejected`).
7. Infrastructure: transient failures, minutes lost, breaker tripped.
8. Critic rejections (link to rejection log).
9. Warnings: scope tolerance hits, test-lock reverts, contract fixes (REVIEW), tree resets.

## 10. Deliverables (as built)

```
Makefile                          preflight / pilotinloop / resume / rollback / report / validate-plan / test-pilotinloop
.github/pilotinloop/
  config.yaml                     everything tunable
  orchestrator.py                 the loop
  runner.py                       Copilot CLI runner (§4.2, §4.3, §4.6)
  plan.schema.json
  prompts/{planner-questions,planner-plan,spec-critic,pattern-critic,test-writer,test-fixer,implementer}.md
  tests/                          50 tests incl. fake Copilot CLI (502/429/401/quota on demand)
  README.md
docs/copilot-cli-findings.md      §4.2 verification
docs/pilotinloop-handoff-v2.md      this document
```

**Integration into the kit (done 2026-09-23):** the loop ships as `pipeline/pilotinloop/` and is installed by
`./install.sh <repo> <system> --with-pilotinloop` into `.github/pilotinloop/` + `Makefile`. Deviations from the text above,
all deliberate: (a) artifact paths follow the pipeline — `requirements.md`, `open-questions.md` and the assumptions log
`decisions.md` live in `.github/requirements/` (configurable under `paths:` in `config.yaml`; `docs/decisions.md` stays
the ADR log); (b) `.wiki/` is the kit's knowledge layer (`AGENTS.md`, `docs/cards/`, instruction files), read-only for
every PilotInLoop role; (c) three dedicated agents — `pilotinloop-planner`, `pilotinloop-spec-critic`, `pilotinloop-plan-critic` — are
passed via `--agent`: purpose-written for stdout `plan.json` / JSON-verdict output and no human to ask, keeping the
card, ADR, dependency and convention checks of `@planner` / `@spec-critic` / `@pattern-critic` (the manual pipeline's
agents are untouched); implementer and test-writer are prompt-only; (d) `@refiner` emits `[check: <ref>]`
tags by default and `@spec-critic` rejects untagged criteria. The existing YAML rail keeps its interactive gates for
the manual pipeline; PilotInLoop is a separate entry point that reuses the same agents.

## 11. Build order — status

1. ✅ Copilot CLI verification → `docs/copilot-cli-findings.md`. Two items remain **unverified** and are
   config-only: exact error strings for 5xx/429/401/quota, and whether `--share` works with `-s`.
2. ✅ Orchestrator skeleton, config, schema validation, one-task-per-call runner, checkpointing, per-task commits
   (test: `test_happy_path_two_tasks`, `test_runner_never_passes_resume_or_continue`).
3. ✅ Checks integration, retry loop keeping the diff, stuck detection.
4. ✅ Guardrails: test lock, new-test allowance, scope, timeout, diff caps, deny-list, budgets, clean start.
5. ✅ Infra handling: classification, backoff, breaker, tree reset with preserved state, preflight health.
   Tests prove a 502 never blocks a task, a tripped breaker leaves the task `pending`, and 401/quota halt
   without backoff.
6. ✅ Planner questions-only mode + criteria tagging validation.
7. ✅ Critic stage + rejection log.
8. ✅ Assumptions protocol + morning report.
9. ⬜ **Dry run on the real repo** with the real CLI on a small, well-specified feature. Then tune
   `failure_patterns` from any `unknown` calls in the logs. Report results.

## 12. When to use this vs. the manual pipeline

PilotInLoop: well-specified features following existing patterns with solid tests. Manual: ambiguous, novel or
cross-cutting features, or weak test areas.

## 13. Non-goals

- No changes to `.wiki/`: read-only for PilotInLoop agents.
- No autonomous requirements refinement. The refiner stays interactive.
- No merging or deploying. Output is a branch for human review.
