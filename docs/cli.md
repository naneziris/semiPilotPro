# CLI reference

Every command finds the project from the current directory: the nearest folder with `.semipilot/config.yaml`, else
the git root. `--repo <path>` (before the command) points it elsewhere.

| Command | What it does | Exit codes |
|---|---|---|
| `semipilot init [--harness copilot\|claude] [--skills copilot,claude\|both] [--here] [--force]` | Config, the skill pack, `AGENTS.md` if you have no instructions file | 0 |
| `semipilot doctor [--live]` | Checks config, harness installed, skills, instructions, checks, knowledge layer; `--live` adds one small model call to check the login | 0 ok · 1 something to fix |
| `semipilot preflight <feature>` | All run checks + the planner's questions; no branch is created | 0 ready · 3 questions to answer · 1 cannot start |
| `semipilot run <feature> [--branch NAME] [--stack] [--no-questions]` | The loop, on a new branch from the current one (alias `pilotinloop`) | 0 completed · 3 your turn (questions, `plan_approval`, `task_review`) · 2 stopped otherwise (incl. `completed_with_blocked`) · 1 cannot start |
| `semipilot status` | Every feature's stage and the next command | 0 |
| `semipilot review [feature] [--agent]` | Prints `report.md`, the review packet first (default: the last run); `--agent` runs the reviewer agent again first | 0 · 1 no report / cannot run |
| `semipilot resume [feature]` | Continues on the run's branch at the stage that stopped (planning, tests or tasks); blocked tasks get fresh attempts; after a `task_review` stop it accepts that task | 0 completed · 3 your turn · 2 stopped · 1 cannot resume |
| `semipilot approve [feature] [--no-run]` | Records your approval of the plan (a `plan_approval` stop) and continues like `resume`; `--no-run` only records it | as `resume` · 1 nothing to approve |
| `semipilot replan <feature> -m "<text>" [--no-run]` | Drops the plan, gives the planner your words (above the critics'), plans again; the new plan stops for approval | as `resume` · 1 refused |
| `semipilot rollback <feature> <task>` | Reverts a task and every task depending on it; marks them pending | 0 · 1 refused |
| `semipilot intake <issue> [--slug NAME]` | Reads a GitHub/GitLab issue (number or URL) into `.semipilot/features/<slug>/issue.md` for `/semipilot-refine` | 0 · 1 could not read it |
| `semipilot mr [feature] [--dry-run] [--force]` | Pushes the run branch and opens a draft merge / pull request from the review packet (alias `pr`) | 0 · 1 refused or failed |
| `semipilot chore [name] [--list] [--dry-run] [--history] [--reset]` | One small unattended fix on its own branch | 0 fixed / nothing to do / waiting for review · 2 did not pass · 1 cannot start |
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

**`approve`, `replan`.** Only for a run stopped with `plan_approval` (`replan` also after `plan_rejected`). Both switch
to the run branch themselves. See [autonomy.md](autonomy.md).

**`mr`, `intake`.** Use `gh` or `glab`, detected from the `origin` remote or set in `forge.provider`. `mr` is the only
command that pushes. See [forge.md](forge.md).

**`chore`.** One run = at most one commit on a new `chore/…` branch, then back to the branch you started from. See
[chores.md](chores.md).

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
