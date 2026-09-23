# PilotInLoop autonomous loop

Automation layer on top of the SemiPilotPro pipeline. Human at the front (refine + answer questions) and the
back (morning review); machines in the middle. Design: `docs/pilotinloop-handoff-v2.md`.

## Layout
```
.github/pilotinloop/
  config.yaml          guardrails, checks, deny-list, failure patterns — everything tunable lives here
  orchestrator.py      the loop: plan → critique → tests-first → implement → report
  runner.py            Copilot CLI runner: fresh process per call, timeout, logging, failure classes, backoff, breaker
  plan.schema.json     schema for plan.json
  prompts/             planner-questions, planner-plan, spec-critic, plan-critic, test-writer, test-fixer, implementer
  tests/               pytest suite with a fake Copilot CLI (502/429/401/quota on demand)
  runs/<run_id>/       per-call logs (untracked via .git/info/exclude)
```
State that the implementer must never see (`plan.json`) lives **outside** the repo in `~/.semipilot-pilotinloop/<repo>/<run_id>/`.
Copilot CLI's path verification blocks reads outside cwd, so this is enforced by the sandbox, not by a prompt.

## Requirements format
`.github/requirements/requirements.md` (written by `@refiner`; path configurable under `paths:` in `config.yaml`) must have an
`## Acceptance Criteria` section where every item carries a check tag — the refiner does this by default:
```
## Acceptance criteria
- Orders over 100 get free shipping [check: test_free_shipping_threshold]
- No type errors introduced [check: typecheck]
```
The `ref` is a substring the orchestrator greps for in locked test files (to run the right tests per task) and
the identifier the planner must reference in `acceptance_checks`. Preflight refuses untagged criteria.

## Usage
```
make preflight FEATURE=free-shipping      # ~10 min interactive: answer .github/requirements/open-questions.md, merge into requirements.md, commit
nohup make pilotinloop FEATURE=free-shipping > pilotinloop.out 2>&1 &
# morning
cat reports/pilotinloop-<date>-free-shipping.md    # assumptions first, then blocked tasks, then diff
make rollback TASK=T3                            # if an assumption was wrong
make resume                                      # continue from the last good checkpoint
```

## Adapting `config.yaml` to a project
- `checks`: the commands that define "done". Keep `{task_tests}` in the tests command so each task only runs
  its own locked tests (plus done tasks'); the full suite runs once at the end.
- `runner.agents`: the dedicated `pilotinloop-planner`, `pilotinloop-spec-critic`, `pilotinloop-plan-critic` agents
  (installed with the pipeline) are passed via `--agent` so the knowledge-layer checks apply. `null` = prompt only.
- `paths`: where requirements / open questions / the assumptions log live (defaults: `.github/requirements/`).
- `runner.deny_tools`: extend for your stack (deploy scripts, package publishers).
- `failure_patterns`: **VERIFY** against real Copilot CLI error output; unknown failures are logged raw under
  `runs/<run_id>/` so you can extend the patterns.
- `tests.patterns` and `tests.contract_error_patterns`: match your test layout and language.

## Tests
```
make test-pilotinloop
```
Covers: fresh-session guarantee (no resume/continue flags ever), failure classification, backoff + breaker,
502 never blocks a task, breaker leaves the task `pending` and `resume` finishes it, 401/quota halt immediately,
retry keeps the failed diff, stuck detection, test lock, new-test allowance, scope check, diff caps, budgets,
contract-fix path, plan validation, critique loop, rollback.
