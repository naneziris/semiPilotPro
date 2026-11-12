# Stop reasons

The report's first lines say why the run stopped. Exit code of `semipilot run` / `resume`: 0 `completed`, 3 waiting
for the human (answers, `plan_approval`, `task_review`), 2 any other stop reason (including
`completed_with_blocked`), 1 could not start. `resume` gives blocked
tasks a fresh set of attempts and continues at whatever stage stopped — planning, tests or implementation.

| Stop reason | Meaning | Next action |
|---|---|---|
| `completed` | Every task done; final full suite ran (exit 0). Check section 4 for its result. | Review → scribe (if knowledge layer) → PR. |
| `completed_with_blocked` | The loop finished, but some tasks are blocked (exit 2); no final full suite. | Read each blocked task's reason in section 2; answer or fix, then `resume`. |
| `blocked` | The planner or test-writer answered `BLOCKED: <question>` — it cannot go on without you. The question is the stop detail. | Answer it in `requirements.md`, then `semipilot resume <feature>` — it continues at the step that stopped (planning or tests). |
| `budget_exhausted` | `max_iterations`, wall-clock, the per-run diff cap or a spend cap (`max_cost_usd`, `max_premium_requests`) was reached. Detail says which. | Decide whether the work is bigger than planned; raise the budget or split the spec, then `resume`. |
| `plan_rejected` | The critics rejected the plan twice, or the planner could not produce a valid plan. | Read `rejection-log.md`; usually the spec is ambiguous or too big. Fix it, `preflight`, `run` again (delete the run branch first). |
| `auth_failure` | The agent CLI is not logged in / token expired. Nothing was blamed on a task. | `copilot login` or `claude` → `/login`, then `resume`. |
| `quota_exhausted` | Premium requests / usage limit / credit balance ran out. Halts immediately, no backoff. | Wait for the reset or raise the limit, then `resume`. |
| `agent_unavailable` | Sustained outage of the agent service tripped the circuit breaker (shown as `copilot_unavailable` by v0.1). | `resume` later. |
| `agent_start_failed` | The agent CLI could not be started at all (e.g. the OS refused its command line). No task was blamed; the checkpoint is saved. | Fix the cause in the detail, then `resume`. |
| `guardrail_violation` | An agent switched branches. The loop switched back (without resetting anything on the other branch) and stopped. | Check the log of that call; `resume`. |
| `rolled_back` | You ran `rollback`; the tasks are pending again. | Fix the spec or decisions, then `resume`. |
| `plan_approval` | The critics accepted the plan and the feature's risk tier (medium or high, or raised by the paths the plan touches) asks a human to read it. Nothing is built yet. | Read `implementation-plan.md`. `semipilot approve <feature>` continues; `semipilot replan <feature> -m "<what to change>"` sends it back to the planner. |
| `task_review` | High risk: a task is done and committed; the run waits before the next one. The detail names the commit. | `git show <sha>`. `semipilot resume <feature>` accepts and continues; `semipilot rollback <feature> <task>` rejects. |
| `replan_requested` | You sent the plan back with `replan --no-run`. | `semipilot resume <feature>` plans again (and stops for approval again). |
| `tests_not_red` | Only with `tests.red_check: halt`: a task's locked tests pass before any implementation exists. | Read those tests. `resume` goes on anyway; otherwise sharpen the criteria and start over. |

A `preflight` that cannot start (exit 1) prints its reason directly: unapproved or missing spec, untagged acceptance
criteria, dirty working tree, existing run branch, starting from another run's branch (use `--stack` to build on
it), unhealthy knowledge layer or unknown tags, `checks` still TODO, or an agent CLI that is not installed. A login problem
shows up as `auth_failure` on the planner's questions call, before any branch exists.
