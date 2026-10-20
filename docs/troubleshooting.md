# Troubleshooting

Start with `semipilot doctor`. Every agent call is logged in `.semipilot/runs/<run-id>/<label>.log` with the
prompt, the agent's answer, stdout, stderr, exit code and classification — that log answers most questions.

## Setup

**`auth_failure` before the run starts, or `doctor --live` fails** — Run the CLI once interactively and log in
(`claude` → `/login`, or `copilot login`). For Claude Code with an API key, set `ANTHROPIC_API_KEY`.

**"Claude Code / GitHub Copilot CLI not found"** — Install it, or set `harnesses.<name>.command` to its full path.

**The skills don't show up in chat.** Check the folder for your chat: `.claude/skills/` for Claude Code,
`.agents/skills/` for Copilot (VS Code chat and CLI). Installed for the other one? `semipilot init --skills both`.
VS Code: `chat.useAgentSkills` must be on (default). Restart the chat session after installing.

**"AGENTS.md filled in [!!]"** — Replace the `{{TODO}}` lines. The plan critic rejects plans while they remain.

**Claude Code ignores AGENTS.md.** You have a `CLAUDE.md`; Claude Code then reads only that. Add a line `@AGENTS.md`.

## Preflight refuses

| Message | Fix |
|---|---|
| `requirements.md not found` | `/semipilot-refine <idea>` in chat |
| `… is not approved` | `/semipilot-spec-critic`, reply `approve` |
| `acceptance criteria without a machine-checkable [check: …] tag` | Tag each criterion (the refiner's acceptance-criteria guide) |
| `working tree is dirty` | Commit or stash. The check is repository-wide on purpose: rollbacks use `git reset --hard` |
| `branch … already exists` | Delete it, or `--branch other-name` |
| `you are on <branch>, the branch of an earlier semipilot run` | `git checkout main`, or `--stack` to build on top of it |
| `knowledge layer unhealthy` | `semipilot kb validate` and fix what it reports |
| `unknown tag(s)` | Fix `Tags:` under Knowledge References in the requirements |
| `check … is still a TODO` | Edit `checks` in `.semipilot/config.yaml` |
| `unknown harness` | `harness: copilot` or `harness: claude` |

## During or after a run

**`plan_rejected`.** Read `rejection-log.md`. Repeated critic rejections usually mean an ambiguous or oversized spec
— fix it and run again (delete the run branch first). If the plan critic says the instructions are empty, fill them.

**A task is blocked: "same error twice".** Read the task's two attempt logs. Typical causes: a locked test that
expects something the spec didn't say (fix the spec, rollback, resume), or an environment problem the agent cannot
fix (a missing service, a flaky test).

**A locked test was changed by the test-fixer.** It may only change imports, names and signatures. The report lists
the edit under *Warnings* — review it like any other diff.

**`auth_failure` mid-run.** The login expired. Log in again and `semipilot resume <feature>`. For long runs on
tokens with a known expiry, set `SEMIPILOT_TOKEN_EXPIRES_AT` so preflight warns you.

**`quota_exhausted`.** Premium requests, usage limit or credit balance ran out. Wait for the reset (or raise the
limit), then `resume`. The interrupted task keeps its attempt count.

**`agent_unavailable`.** The service was down long enough to trip the breaker. `resume` later, or set
`infra.retry_window` to resume once automatically.

**Calls classified `unknown`.** A failure text no pattern recognised: retried once, then counted against the task.
Copy a distinctive fragment of the stderr from the log into your config:

```yaml
failure_patterns:
  transient: ["the distinctive fragment"]     # or fatal / quota_exhausted
```

**`guardrail_violation`.** An agent switched branches despite the deny rules. The loop switched back and stopped;
look at that call's log, then `resume`.

**The final full suite failed although every task passed.** Tasks interfere (shared state, ordering). The report's
warning shows the failure; usually a new requirement or a fix by hand.

**Cost is higher than expected (Claude Code).** Each call is a fresh session and pays Claude Code's startup context.
The report's cost by role shows where it goes; see [harnesses.md](harnesses.md#cost-and-speed) for what to change, in
order of effect.

## Knowledge layer

| Error | Fix |
|---|---|
| `tag "x" is not in _vocabulary.md` | Use an existing tag, or add one in a reviewed change |
| `code path does not exist` | The code moved; update the card, then `kb index` |
| `manifest.json is stale` | `semipilot kb index`, commit it |
| `DRIFT undeclared dependency X -> Y` | Add Y to X's `depends_on`, or remove the import |
| `no source files … under src` | Set `srcDirs` / `extensions` in `scripts/kb/kb.config.json` |
| The hook doesn't run | `git config core.hooksPath .githooks` (the path `kb init` printed, in a monorepo) |

## Getting help

Open an issue with the output of `semipilot --version`, `semipilot doctor`, the stop reason, and the relevant call
log (remove anything confidential first).
