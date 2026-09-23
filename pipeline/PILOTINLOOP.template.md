# PILOTINLOOP — running a feature unattended in {{REPO_NAME}}

The manual pipeline (`INSTRUCTIONS.md`) keeps you in the loop at every step. PilotInLoop keeps you at the **front**
(refine, answer the planner's questions) and the **back** (morning review) and lets a Python orchestrator run the
middle: plan → two critic gates → locked tests → implement task by task → checks → report. Design of record:
`docs/pilotinloop-handoff-v2.md`. Configuration: `.github/pilotinloop/config.yaml`.

**Use it for** well-specified features that follow existing patterns in areas with a solid test suite.
**Do not use it for** ambiguous, novel or cross-cutting work, or areas where the tests are weak — the loop's
definition of done is "all configured checks pass", so weak checks produce confidently wrong code.

## 0. One-time setup

```bash
pip install pyyaml jsonschema pytest        # jsonschema ≥ 4; pytest only for the loop's own tests
copilot login                               # or export COPILOT_GITHUB_TOKEN / GH_TOKEN
which copilot make python3                  # all three on PATH, from the repo root
```

Edit `.github/pilotinloop/config.yaml`:

| Key | Set it to |
|---|---|
| `checks` | the commands that define "done", fast first. Keep `{task_tests}` in the tests command: it expands to the current task's locked test files (plus done tasks'), empty for the final full-suite run. Example for TS: `npm run lint`, `npm run typecheck`, `npx vitest run {task_tests}`, `npm run build`. |
| `tests.patterns` | globs that match your test files — these are what the test lock protects. |
| `tests.contract_error_patterns` | error strings that mean "the test guessed a wrong name/signature" in your language (defaults cover Python, TS, Go). |
| `runner.deny_tools` | extend with anything dangerous in your stack (deploy scripts, publishers, migrations against shared DBs). |
| `runner.model` | pin a model for reproducibility, or leave `null` for the CLI default. |
| `budget.*`, `guardrails.*` | defaults are conservative (3 retries/task, 30 implementer calls, 6 h, 400/3000 diff lines). Loosen only after a few good runs. |
| `paths.*` | only if your requirements do not live in `.github/requirements/`. |

Then prove the machinery works before trusting it with a night:

```bash
make test-pilotinloop        # 50 tests against a fake Copilot CLI (502/429/401/quota on demand)
```

## 1. Evening — 10–15 minutes, interactive

1. **Refine as usual.** `@refiner <idea>` in VS Code chat → `.github/requirements/requirements.md`. Confirm the
   tags, answer its questions. Every acceptance criterion must end with a `[check: <ref>]` tag — `@refiner` does this
   by default; `<ref>` is a test name or unique test-name substring, or `lint` / `typecheck` / `build`. Run
   `@spec-critic` and approve the spec exactly as in the manual flow — this is the intent check, and the last cheap
   point to fix a misread idea.
2. **Clean tree, real branch.** Commit everything. The loop refuses a dirty tree and creates
   `pilotinloop/<slug>-<date>` from your current HEAD; it never pushes.
3. **Preflight.**
   ```bash
   make preflight FEATURE=<slug>
   ```
   It validates the `[check:]` tags, refuses a dirty tree or an existing run branch, makes one trivial Copilot CLI
   call, runs `gh auth status` (configurable), refuses to start if `COPILOT_TOKEN_EXPIRES_AT` is set and earlier than the
   wall-clock budget, prints an upper bound on Copilot requests, then runs `@pilotinloop-planner` in
   **questions-only mode** → `.github/requirements/open-questions.md`.
4. **Answer every question inline**, merge the answers into `requirements.md` (edit the relevant section — the
   planner reads the requirements, not the questions file), commit. Unanswered ambiguity becomes either a logged
   assumption (`decisions.md`) or a `BLOCKED` task at 3 am; five minutes here is the best-leveraged time of the run.
5. **Launch.**
   ```bash
   nohup make pilotinloop FEATURE=<slug> > pilotinloop.out 2>&1 &
   tail -f pilotinloop.out          # optional; every stage logs a line
   ```
   Laptop lid closed = sleep = no run. Use a machine that stays awake (the DevPod container, a desktop, `caffeinate`).

## 2. Night — what runs, in order

| Stage | What happens | If it fails |
|---|---|---|
| Plan | `@pilotinloop-planner` emits `plan.json` (tasks ≤ 5 files, `S`/`M`, `interfaces`, check refs). Validated against the schema + sizing + coverage. | one re-prompt with the errors, then halt `plan_rejected` |
| Critique | `@pilotinloop-spec-critic` (coverage, feasibility, edge cases, cards) and `@pilotinloop-plan-critic` (sizing, ownership, conventions, invariants, contracts). Rejections → `.github/rejection-log.md` → re-plan. | 2 rejected rounds → halt `plan_rejected` |
| Tests first | test-writer turns criteria into **one test file per task**, built only against the plan's `interfaces`. Files are checksum-locked and committed (`[pilotinloop] tests: locked acceptance tests`). | non-test files it touched are reverted |
| Implement | per task, in dependency order: fresh Copilot CLI process, narrow prompt (task + requirements + decisions + its files + locked test list + last errors). Then the orchestrator runs: timeout → test lock → scope → diff cap → `checks`. Failure → retry **with the failed diff still in the tree**. Pass → `[pilotinloop] T<n>: <title>` commit. | same error twice → BLOCKED; 3 attempts → BLOCKED; dependents BLOCKED |
| Contract fix | locked test fails on an import/name/signature error → one logged test-fixer call (names/imports only), re-lock, re-check. | counted as a REVIEW warning in the report |
| Final checks | after the last task, the full suite once. | loud warning in the report; tasks stay done — you decide |
| Report + state | `reports/pilotinloop-<date>-<slug>.md`, then one `[pilotinloop] state: <reason>` commit with `decisions.md`, progress, rejection log. | — |

Infrastructure is handled separately from task failures: 5xx/429/network → backoff 1→16 min (cap 15) and retry the
**same** call without consuming a task attempt; 90 min continuous or 150 min total outage → circuit breaker, the
interrupted task goes back to `pending`, halt `copilot_unavailable`; 401/403 → halt `auth_failure`; quota text →
halt `quota_exhausted` immediately (waiting does not refill it). Per-call logs (prompt, stdout, stderr, classification):
`.github/pilotinloop/runs/<run_id>/` (untracked).

## 3. Morning — review in this order

```bash
cat reports/pilotinloop-<date>-<slug>.md
```

1. **Assumptions first** (`.github/requirements/decisions.md`, section 1 of the report). Each `D-<n>` names the task,
   the ambiguity, the choice, the alternatives and how to undo it. A wrong assumption is the expensive failure mode —
   read these before the diff.
2. **Blocked tasks** and their reason/question. `BLOCKED: <question>` is the implementer asking you.
3. **Completed tasks** with commit SHAs, then check results (final suite), diff stats, budget and stop reason
   (`completed`, `budget_exhausted`, `copilot_unavailable`, `auth_failure`, `quota_exhausted`, `plan_rejected`),
   infrastructure summary, critic rejections, warnings (scope-tolerance hits, test-lock reverts, contract fixes,
   tree resets).
4. **Act:**
   ```bash
   make rollback TASK=T3      # wrong assumption: git-reverts T3 and its dependents (newest first), sets them to pending
   make resume                # continue from the first non-done task on the same branch (also after an outage)
   make report                # regenerate the report from the checkpoint
   ```
   Fix the requirements or `decisions.md` before `resume` if the assumption was wrong — resume re-prompts with the
   current requirements.
5. **Finish like a manual run.** Review the diff, run `@scribe` (the loop never touches the knowledge layer — cards,
   instructions, ADRs, changelog are still yours to update), then the normal commit/PR review. The run branch is
   never pushed by the loop.

## 4. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `preflight`: "acceptance criteria without a machine-checkable [check: ...] tag" | Add `[check: <ref>]` to every criterion in `requirements.md`. |
| `preflight`: "working tree is dirty" / "branch already exists" | Commit or stash; delete the old `pilotinloop/<slug>-<date>` branch or pick another slug. |
| `preflight`: "Copilot CLI health check failed" | `copilot login`, or check `runner.command`. The raw output is printed. |
| Halt `plan_rejected` after 2 rounds | Read `.github/rejection-log.md`. Usually the requirements are underspecified or a card is missing (the critic says "needs a human"). Fix, re-run `preflight`. |
| A task BLOCKED with the same error twice | Read `.github/pilotinloop/runs/<run_id>/T<n>-attempt*.log`. Often a wrong locked test or an ambiguity — answer it in the requirements, `rollback` if needed, `resume`. |
| Halt `copilot_unavailable` | Outage breaker tripped; the task is `pending`. `make resume` when the service is back (or set `infra.retry_window` to auto-resume once at e.g. `05:00`). |
| Calls classified `unknown` in the logs | The CLI's error text is not in `failure_patterns`. Add the stderr signature to the right class (`fatal` / `quota_exhausted` / `transient`) in `config.yaml`. |
| Test-writer or implementer modified a locked test | Reverted automatically, attempt consumed; visible in the report's warnings. Recurring → the criterion's `[check:]` ref is probably wrong. |
| Report says the final full suite failed but tasks are done | Interaction between tasks the per-task runs could not see. Decide in review; the loop does not guess. |

## 5. What the loop will never do

Push, merge, deploy, install packages, touch the knowledge layer, refine requirements, resume a Copilot session
(`--resume`/`--continue` are refused by the runner), read `plan.json` from the implementer's side (it lives in
`~/.semipilot-pilotinloop/<repo>/<run_id>/`, outside the repo), or decide on its own that work is done.
