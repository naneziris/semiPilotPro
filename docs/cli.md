# CLI reference

Every command finds the project from the current directory: the nearest folder with `.semipilot/config.yaml`, else
the git root. `--repo <path>` (before the command) points it elsewhere.

| Command | What it does | Exit codes |
|---|---|---|
| `semipilot init [--harness copilot\|claude] [--skills copilot,claude\|both] [--here] [--force]` | Config, the skill pack, `AGENTS.md` if you have no instructions file | 0 |
| `semipilot doctor [--live]` | Checks config, harness installed, skills, instructions, checks, knowledge layer; `--live` adds one small model call to check the login | 0 ok · 1 something to fix |
| `semipilot preflight <feature>` | All run checks + the planner's questions; no branch is created | 0 ready · 3 questions to answer · 1 cannot start |
| `semipilot run <feature> [--branch NAME] [--stack] [--no-questions]` | The loop, on a new branch from the current one (alias `pilotinloop`) | 0 completed · 2 stopped (incl. `completed_with_blocked`) · 3 questions · 1 cannot start |
| `semipilot status` | Every feature's stage and the next command | 0 |
| `semipilot review [feature]` | Prints `report.md` (default: the last run) | 0 · 1 no report |
| `semipilot resume [feature]` | Continues on the run's branch at the stage that stopped (planning, tests or tasks); blocked tasks get fresh attempts | 0 completed · 2 stopped · 1 cannot resume |
| `semipilot rollback <feature> <task>` | Reverts a task and every task depending on it; marks them pending | 0 · 1 refused |
| `semipilot kb init [--system PREFIX] [--force]` | Installs the knowledge layer | 0 |
| `semipilot kb <validate\|index\|resolve\|drift\|guard\|catchup> …` | Runs `scripts/kb/kb.py` (or the bundled copy) | as `kb.py` |
| `semipilot config` | Prints the effective configuration | 0 |
| `semipilot --version` | | 0 |

## Notes

**`init`.** `--here` makes the current directory the project even inside a bigger repository (monorepo). Re-running
`init` after an upgrade replaces `semipilot-*` skill folders from an older version; `--force` reinstalls them even when
current. Your `.semipilot/config.yaml` and instructions file are never overwritten; on an existing config,
`--harness` changes only the `harness:` line.

**`run`.** Start on the branch the feature should be built on (usually `main`). Refused when: the spec is missing,
unapproved or has untagged criteria; the tree is dirty (uncommitted spec and answers in the feature folder are
committed for you); the run branch exists (`--branch` names another); you are on the branch of an earlier run
(`--stack` builds on top of it on purpose); `checks` contain a TODO; the knowledge layer is unhealthy or a tag is
unknown; the agent CLI is not installed. (A login problem shows up on the first real call — the planner's questions —
and stops cleanly before any branch exists.) `--no-questions` skips the planner's questions; it logs assumptions instead.

**`rollback`.** Adds `git revert` commits for the task and its dependents (in reverse order) and resets their state.
It refuses on a dirty tree. A conflicting revert stops with a message; resolve it by hand.

**Commits and hooks.** The loop's own commits (tasks, locked tests, run state, reverts) are made with `--no-verify`:
a project hook must not be able to crash an unattended run halfway through a task. Your CI still checks the branch,
and your own commits on it run the hooks as usual.

**`kb`.** `semipilot kb resolve --tags a,b` equals `python3 scripts/kb/kb.py --root <project> resolve --tags a,b`.
`semipilot kb --help-tool` shows the tool's own help.

## Running without pip

`bin/semipilot` (macOS/Linux) and `bin\semipilot.cmd` (Windows) run `python -m semipilot` with `src/` on the path.
`PYTHON=/path/to/python3 bin/semipilot …` picks the interpreter. Windows is supported by the launcher and the code
paths, but CI covers Linux and macOS only.

## Environment

| Variable | |
|---|---|
| `SEMIPILOT_TOKEN_EXPIRES_AT` | ISO timestamp of the agent token's expiry; preflight refuses when the run could outlive it |
| `PYTHON` | interpreter used by `bin/semipilot` |

Agent credentials are the harness's own: `copilot login` / `COPILOT_GITHUB_TOKEN`, or Claude Code's login /
`ANTHROPIC_API_KEY`. semiPilot never reads or stores them.
