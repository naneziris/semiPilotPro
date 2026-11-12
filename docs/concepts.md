# Concepts

## The principle

> Keep the human at the **front** and the **back**. Remove the human from the **middle**.

Requirements mistakes are expensive: a misread idea becomes a large, coherent, wrong diff. Implementation mistakes
are cheap: a failing check is information, and a loop can act on it. So human time goes to intent (what, why, and
how we will know it works) and to review; machines do the middle under rules they cannot negotiate.

Two refinements since 0.3. **The middle is not the same for every feature**: a loop may run alone only as far as
its result can be verified cheaply, so each feature carries a risk tier that says where a person looks —
nowhere (`low`), at the plan (`medium`), at the plan and every task (`high`). And **the back is prepared**: the one
step that does not scale is a person reading the result, so the report opens with a packet that tells them where to
read first. Both are in [autonomy.md](autonomy.md).

## The flow

| Step | Who | Where | Output |
|---|---|---|---|
| 0. Intake (optional) | `semipilot intake <issue>` | terminal | `issue.md` — the issue as source material |
| 1. Refine | you + `semipilot-refine` | agent chat | `requirements.md` (draft) — acceptance criteria tagged `[check: <ref>]`, a proposed `risk:` tier |
| 2. Gate 1 | `semipilot-spec-critic`, then **you** | agent chat | `status: approved` — the one approval |
| 3. Questions | planner (questions-only), then **you** | terminal + editor | `open-questions.md`, answered |
| 4. Plan | planner | loop | `plan.json` → `implementation-plan.md` |
| 5. Gates 2a/2b | plan-fidelity critic, plan critic | loop | accept, or reject with fixes (2 rounds max) |
| 5b. Plan approval | **you**, at `medium` and `high` risk | terminal | `semipilot approve`, or `semipilot replan -m "…"` |
| 6. Tests first | test-writer, then the red check | loop | one locked test file per task, committed; each must fail before the code exists |
| 7. Implement | implementer, one fresh process per task | loop | one commit per task, or a blocked task |
| 7b. Task review | **you**, at `high` risk | terminal | `semipilot resume` (accept) or `semipilot rollback` after each task |
| 8. Verify | the orchestrator | loop | your checks after every attempt; full suite at the end |
| 8b. Reviewer | reviewer, read-only, once | loop | a rubric verdict, findings, what to read first |
| 9. Report | the orchestrator | loop | `report.md` opening with the review packet, `decisions.md`, a PR draft |
| 10. Review | **you** (+ `semipilot-run`) | terminal + chat | rollback / resume / accept |
| 11. Close | `semipilot-scribe`, then **you** | agent chat + terminal | cards and docs in sync; `semipilot mr` opens the draft request |

## Tagged acceptance criteria

Every criterion ends with `[check: <ref>]`, naming the test (or `lint` / `typecheck` / `build`) that proves it.
This is the contract that lets the middle run unattended:

- preflight refuses a spec with an untagged criterion;
- the planner may only reference tagged refs, and plan validation checks coverage **both ways** (every ref covered by
  a task, every task's refs real);
- the test-writer names one test after each ref;
- each task's test run is scoped to the test files containing its refs (`{task_tests}`).

## The roles

| Role | Permission profile | Sees | Produces |
|---|---|---|---|
| planner | read | requirements, answers, instructions, resolved knowledge, the code | questions, or the plan JSON |
| plan-fidelity critic | read | the plan, requirements, answers, knowledge | `{"verdict", "issues"}` — does the plan deliver the approved spec (it does not review the spec again; Gate 1 did) |
| plan critic | read | the plan, instructions, area rules, cards, dependency policy | `{"verdict", "issues"}` — conventions, sizing, contracts |
| test-writer | write | criteria, task interfaces, test conventions | locked tests, one file per task |
| implementer | write | **one task only**, requirements, answers, decisions, the locked tests' names | code for that task |
| test-fixer | write | a contract error (import/name/signature) in a locked test | a minimal, logged fix — never an assertion change |
| reviewer | read | requirements, answers, decisions, the plan, the whole diff (read-only git) | `{"verdict", "rubric", "findings", "read_first"}` — advice for the human, never a gate |
| chore | write | **one finding** and the chore's instruction (`semipilot chore` only) | one small fix |

Each role is a prompt the orchestrator composes for every call: the role definition (`src/semipilot/roles/`) followed
by the task. Nothing depends on harness-specific agent files, so the same roles run on Copilot CLI and Claude Code.
The implementer never sees the plan: `plan.json` lives outside the repository during the run.

## What the orchestrator enforces

After every agent call, independent of what the agent says it did:

| Rule | On violation |
|---|---|
| Locked tests unchanged (SHA-256 per file) | changes reverted, attempt counted, the agent told why |
| Only the task's files (+ a small tolerance), never another task's | attempt reverted; twice → task blocked |
| Diff ≤ per-task cap; run total ≤ per-run cap | task blocked / run stops |
| The run branch is still checked out | run halts (`guardrail_violation`) and switches back |
| All configured checks pass | retry with the failed diff still in place and the errors in the prompt |
| The same error twice | task blocked (stuck), tree reset to the last good commit |
| A contract error in a locked test | one logged test-fixer pass; the change is flagged for review |
| Locked tests fail before any implementation (red check) | a task whose tests already pass is flagged in the report (`tests.red_check: halt` stops the run) |
| The tier's gates: plan approved by a human, each task accepted | the run stops with `plan_approval` / `task_review` and waits |
| The reviewer changed nothing | anything it touched is reset |
| Spend under `budget.max_cost_usd` / `max_premium_requests` | the run stops between tasks (`budget_exhausted`) |

**Done means your checks pass.** The agent is never asked whether it is finished.

## Assumptions, not guesses

When the spec is silent, an agent must either choose the **most reversible** option and log it in `decisions.md`
(what was unclear, what it chose, the alternatives, how to undo it), or stop with `BLOCKED: <question>`. The report
puts these assumptions first, because a wrong one is the thing you most need to catch. `rollback` reverts a task and
everything that depends on it, so fixing a wrong assumption costs one command.

## Failures that are not the task's fault

Every call is classified: ok · task failure · transient · fatal · quota · unknown.

- **Transient** (5xx, 429, overloaded, network): exponential backoff with jitter, the tree reset, the same call
  retried; the task's attempt counter is untouched. A circuit breaker stops the run after a sustained outage
  (`agent_unavailable`); `resume` continues.
- **Fatal** (not logged in, bad credentials) and **quota** (premium requests, usage limit, credit balance): halt
  immediately — waiting would not help.
- **Unknown**: treated as transient once, then as a task failure; the raw output is in the call log.

## The knowledge layer (optional)

With `docs/cards/` and `scripts/kb/kb.py`, the requirements name 1–4 tags; the orchestrator resolves them once
(`kb resolve`) and gives every agent the same exact reading list — cards, deep docs, code paths. Agents need no
shell access to retrieve knowledge, and nobody greps. The planner lists *Knowledge Updates Required*; the loop never
writes to cards or instructions — `semipilot-scribe` does, after your review. See
[knowledge-layer.md](knowledge-layer.md).

## When not to use the loop

- No meaningful test suite in the area you are changing — fix that first, or use the skills interactively.
- Exploratory work where you do not yet know what "done" looks like.
- Changes that are mostly judgement: UX polish, naming, architecture direction.
- Very large changes. The refiner proposes a first slice above ~8 tasks; take it.
- Faster than you can read. One reviewed feature at a time beats three unread ones; the loop has no parallel mode on
  purpose — your review is the bottleneck, and running more loops only deepens the pile in front of it.

The skills are useful on their own in all of these cases: a tagged spec reviewed at Gate 1 makes interactive agent
work better too.
