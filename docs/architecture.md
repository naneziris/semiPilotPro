# Architecture

```
src/semipilot/
  cli.py            commands; finds the project; init/doctor/status/review output
  orchestrator.py   the loop: preflight, plan + critique, locked tests, per-task implement/verify, report, rollback
  runner.py         one call = one process: timeout, logging, classification, backoff, circuit breaker
  harness.py        adapters: role + permission profile + prompt → argv/stdin; output → answer + metadata
  roles/            role definitions inlined before the task prompt (planner, plan-fidelity-critic, plan-critic)
  prompts/          task prompts with {placeholders} (planner-questions, planner-plan, critics, test-writer, …)
  config.py         defaults + project config; layout; knowledge-layer and instructions-file detection
  defaults.yaml     every default, including each harness's allow/deny rules and failure patterns
  initcmd.py        `init`: detect stack, write config, install skills, AGENTS.md
  kbcmd.py          `kb init` and the passthrough to kb.py
  skills_pack.py    locate the skill pack (wheel or checkout) and copy it into a project
  detect.py         stack detection → checks and test patterns
  plan.schema.json  the plan contract
  _vendor/yaml      bundled PyYAML (used only when PyYAML is not installed)
skills/             the Agent Skills pack — also the source of kb.py and the knowledge templates
```

## One call, end to end

1. The orchestrator renders the prompt: `roles/<role>.md` (if the step has a role) + `---` + `# Your task` +
   `prompts/<name>.md`, both filled with the same variables (requirements path, criteria, plan, task, knowledge
   context, instructions files). Project overrides in `.semipilot/roles/` and `.semipilot/prompts/` win.
2. `Runner.run(role, prompt, label)` asks the adapter for an `Invocation(argv, stdin)` using the role's permission
   profile (`roles:` in the config). The adapter refuses forbidden flags.
3. The process runs with a timeout in the project directory. The adapter extracts the answer and metadata (Claude
   Code: the JSON `result`, `is_error`, `total_cost_usd`, `permission_denials`).
4. The call is classified (`ok`, `task_failure`, `transient`, `fatal`, `quota_exhausted`, `unknown`) by exit code,
   `is_error` and the harness's failure patterns, and logged to `.semipilot/runs/<run-id>/<label>.log`.
5. Transient/unknown-once → reset the tree, back off, retry the same call. Fatal/quota → `HaltRun`. A sustained
   outage trips the breaker → `HaltRun("agent_unavailable")`.
6. The orchestrator verifies the effect (branch, test lock, scope, diff size, checks) and decides: commit, retry with
   the errors, test-fixer, or block.

## State

- `implementation-progress.json` (in the feature folder) is the checkpoint: tasks with status, attempts, commit,
  blocked reason, diff stats; budget used; infra summary; the test lock's checksums; critique history.
- `plan.json` lives in `state_dir` during the run (outside the repository) and is copied into the feature folder at
  the end, so `resume` and `rollback` work after the state dir is gone.
- Orchestrator-managed paths (the feature folder, `runs/`) are preserved across tree resets, excluded from task
  commits, and committed separately as `chore(<feature>): run state (…)`.
- Every task commit contains only that task's code: `feat(<feature>): <title> (T<n>)`. The loop commits with
  `--no-verify` (reverts too), so project hooks cannot crash a run.
- `resume` continues at the stage that stopped: no plan yet → plan; tests not locked yet → write them; then the
  tasks, with blocked tasks given a fresh set of attempts.
- A tree reset never runs on another branch: if an agent switched branches, the orchestrator switches back and halts.

## Why inline roles instead of harness agent files

v0.1 loaded the planner and critics as Copilot custom agents (`--agent`). That tied the loop to one harness's agent
format. Inlining the role in the prompt gives the identical instructions on every harness; the one thing custom
agents added — restricted tools — moved to permission profiles that each adapter maps to its CLI's own rules, and
which the orchestrator backs up by verifying effects after every call. The knowledge context moved too: the
orchestrator resolves the tags itself and puts the reading list in the prompt, so read-only roles need no shell.

## Adding a harness

1. **Adapter** in `harness.py`:

   ```python
   class CodexHarness(Harness):
       name = "codex"
       label = "OpenAI Codex CLI"
       default_command = "codex"
       install_hint = "install the Codex CLI and log in"
       login_hint = "codex login"
       hard_forbidden = ("resume", "--last")           # anything that resumes a session or bypasses rules

       def _command(self, role, profile, prompt, log_dir):
           sandbox = {"read": "read-only", "write": "workspace-write", "none": "read-only"}[profile]
           return Invocation(self.executable + ["exec", "--json", "--sandbox", sandbox, "-"], stdin=prompt)

       def response(self, stdout):
           ...                                         # last agent message from the JSONL events; cost if reported

   HARNESSES = {h.name: h for h in (CopilotHarness, ClaudeCodeHarness, CodexHarness)}
   ```

2. **Defaults** in `defaults.yaml` under `harnesses.codex`: `command`, `allow`/`deny` (or nothing, if the CLI only
   has sandbox levels — then the orchestrator's after-the-fact checks are the guardrail), `failure_patterns`.
3. **Skills folder** in `skills_pack.SKILL_DIRS` (Codex reads `.agents/skills/`, which Copilot already uses).
4. **Tests:** add the dialect to `tests/fake_agent.py`, the name to `HARNESSES` and its real error strings to
   `ERRORS` in `tests/conftest.py`. The whole orchestrator suite then runs against it.
5. **Verify for real**: flags against `--help`, one `doctor --live` call, one write-profile call that must be denied
   `git push`, one read-profile call that must be denied a write. Record the result in
   [harnesses.md](harnesses.md#what-has-been-verified).

## Design records

- [design/pilotinloop-handoff-v2.md](design/pilotinloop-handoff-v2.md) — the loop's design of record: every rule
  and the bug it fixes.
- [design/copilot-cli-findings.md](design/copilot-cli-findings.md) — what Copilot CLI verifiably supports headless.
