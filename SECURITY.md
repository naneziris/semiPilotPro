# Security

semiPilot runs AI agents unattended on your machine, in your repository. This page says exactly what they can and
cannot do, and how to report a problem.

## What the loop can do

- **Read** the project. Read-only roles (planner, critics) can do nothing else except read-only `git` commands.
- **Edit files and run commands** in the project directory — only the test-writer, test-fixer and implementer, so they
  can write code and run your tests. On Claude Code this is `Edit`/`Write`/`Bash`; on Copilot CLI `write`/`shell`.
- **Spend your agent quota or money.** Every call is a full agent session. Budgets cap iterations and wall-clock time;
  on Claude Code `max_budget_usd_per_call` caps each call.

## What it cannot do

Denied on every call by the harness's own permission rules (deny wins over any allow):
`git push`, `git commit`, `git reset`, `git clean`, `git checkout`, `git switch`, `git branch`, `git stash`,
`git rebase`, `git merge`, `rm`, `sudo`, `npm install`, `pip install`, `npm publish`, `docker`, `kubectl`,
`terraform`, `curl`, `wget`, and web access. Flags that would disable these rules (`--allow-all-tools`, `--yolo`,
`--dangerously-skip-permissions`, `bypassPermissions`, …) and every session-resume flag are refused before a
process starts.

Verified after every call, independent of the agent: the run branch is still checked out; locked tests are unchanged;
only the task's files changed; the diff is within its cap; your checks pass. Violations are reverted or stop the run.
A tree reset never runs on a branch other than the run branch.

On Claude Code, settings files are not loaded for loop calls (`--setting-sources ""`), so a repository's
`.claude/settings.json` cannot widen a role's permissions, and `Read`/`Edit` on the state dir are denied. Claude Code's
`Read` is otherwise not confined to the project directory; read-only roles can read files elsewhere on the machine
that your user can read.

The loop **never pushes, merges or opens a pull request.** A human reviews the branch.

## Limits you should know

- Shell access for writing roles is broad by design (tests must run). A determined agent could run a command the deny
  list does not name. The orchestrator's after-the-fact checks catch changes to the repository, not side effects
  elsewhere. **Run the loop in a dev container or VM** when the repository or its dependencies are untrusted, and
  never with credentials it does not need (deploy keys, cloud admin tokens) in the environment.
- Pattern rules match command prefixes, not intent: `Bash(rm *)` does not stop `find … -delete`, and
  `Bash(git push *)` does not stop `git -C . push` or `python -m pip install`. Treat the deny list as a seatbelt, not a
  sandbox.
- The loop's commits skip git hooks (`--no-verify`) so a hook cannot crash an unattended run; CI must check the branch.
- Prompt injection: an agent reads your code, issues and docs. Content in them can try to steer it. The guardrails
  above bound what a steered agent can do to the repository; they do not make it trustworthy.

## The skills and `kb.py`

The skills are Markdown instructions. The only script, `skills/semipilot-knowledge/scripts/kb.py`, uses the Python
standard library and read-only `git`; it writes `docs/cards/manifest.json` (`index`) and `.git/kb-last-sync`
(`catchup --mark`) and nothing else. No network access, no installs, no elevated permissions.

## Data

semiPilot sends nothing anywhere itself. Prompts go to whichever agent CLI you configured, under that provider's
terms. Per-call logs (prompts and outputs) stay in `.semipilot/runs/`, which is git-ignored. semiPilot never reads or
stores your agent credentials.

## Reporting a vulnerability

Please report privately through GitHub's *Report a vulnerability* (Security tab of the repository) rather than a
public issue. Include the version, the harness, and the smallest reproduction you can.
