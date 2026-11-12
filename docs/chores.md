# Chores: one small unattended fix per run

A feature needs a person at both ends. Some work does not: fixing one lint finding, removing one needlessly
optional parameter, deleting one dead export. The check for "done" is cheap, runs every time and is hard to fake —
which is exactly the condition under which a loop may run with nobody watching.

`semipilot chore` does **one** such fix per run, on its own branch, and keeps it only if a purely mechanical gate
passes. Schedule it, and you come back to a slightly better codebase and a diff short enough to read.

## Set one up

```yaml
# .semipilot/config.yaml
chores:
  items:
    - name: lint
      find: "npx eslint . --format unix"            # prints one finding per line; the exit code is ignored
      match: "^[^:]+:\\d+:\\d+:"                      # optional: only lines matching this are findings
      instruction: "Fix this ESLint finding in the code. No eslint-disable comments."
      checks: [lint, typecheck, tests]              # optional: which of your `checks` gate it (default: all)
    - name: optional-props
      instruction: "Find one React prop typed as optional that every caller passes, and make it required."
```

`find` is any command that lists what is wrong, one finding per line (`ruff check --output-format concise`,
`grep -rn "TODO(remove)" src`, a script of your own). A chore without `find` is *instruction-only*: the agent looks
for one instance itself, and only your checks and the size caps gate it — weaker, so keep such chores to changes
your checks really cover.

```bash
semipilot chore --list        # every chore and how many findings it has; changes nothing
semipilot chore --dry-run     # which finding the next run would fix
semipilot chore               # one run: the first chore with something to do
semipilot chore lint          # one run of that chore
semipilot chore --history     # the last 20 runs
semipilot chore --reset       # forget remembered failures (skipped findings are tried again)
```

## What one run does

1. Refuses a dirty tree. Runs your checks on the branch you are on: **if they fail there, nothing is attempted** —
   a fix cannot be verified against a red base.
2. Picks the next finding (first in the finder's output that is not skipped or already waiting on a branch).
3. Creates `chore/<name>-<date>-<id>`, locks **every existing test file**, and makes one agent call with the `chore`
   role: fix exactly this one, nothing else.
4. The gate — all of it must hold:
   - at most `max_files` files (3) and `max_diff_lines` changed lines (80);
   - no existing test file changed; no instructions file, `.github/instructions/` or `docs/cards/` changed;
   - your checks pass;
   - with a `find` command: the finding is gone **and** there are fewer findings than before. Moving it, hiding it
     behind a suppression that the finder still reports, or creating a new one does not pass.
5. Pass → one commit (`chore(lint): fix src/a.ts:12:5 …`), you are back on the branch you started from, and with
   `chores.open_mr: true` the branch is pushed and a small request opened ([forge.md](forge.md)).
   Fail → one retry with the errors; then the branch is deleted and nothing is kept.

The agent may answer `BLOCKED: <why this is not a small fix>`; that finding is skipped from then on. A finding that
fails `skip_after_failures` times (2) is skipped too. An agent outage or exhausted quota (`halted`) blames nothing:
the same finding is tried next time.

There is no planner, no critic and no reviewer in a chore: one call, one mechanical gate. That is the point — and
the reason a chore must stay small.

## Chores never outrun the reader

Unread branches are debt. Two rules keep chores behind your review capacity instead of ahead of it:

- A finding whose fix is still on an **unmerged chore branch** is not fixed a second time; the next run takes the
  next finding.
- When `max_open` (3) chore branches are waiting, a run does nothing (`waiting_for_review`, exit 0) until one is
  merged or deleted. Raise it only if you really read that many.

A branch counts as waiting while it exists locally and is not merged into the branch you run from — so pull and
prune after merging requests on the forge, or delete the local branch.

## Scheduling

`semipilot chore` is one run. Anything that can run a command on a schedule can call it; it needs the repository,
your checks' toolchain, and the agent CLI logged in.

```cron
# every weekday at 06:30, on a machine that is awake
30 6 * * 1-5  cd ~/work/app && git checkout -q main && git pull -q --ff-only && semipilot chore >> ~/.semipilot/chore.log 2>&1
```

In CI (a scheduled GitHub Actions workflow or GitLab pipeline schedule) the job additionally needs credentials for
the agent CLI and, with `open_mr: true`, for `gh` / `glab` — and permission to push a branch. Start with cron on
your own machine and `open_mr: false`; move it to CI once you trust what it produces.

Exit codes: 0 fixed, nothing to do, or waiting for review · 2 the fix did not pass its gate, was blocked, or the
agent could not run · 1 cannot start (dirty tree, no chores configured).

## Where the memory is

`chores.json` under `state_dir` (default `~/.semipilot/state/<project>/`): remembered failures and the last 200
runs with their usage. It is outside the repository on purpose — a chore never leaves a file in your working tree.
Call logs are in `.semipilot/runs/chore-<name>-<timestamp>/` (git-ignored), like any run.

## Limits

- **Your checks are the ceiling**, here more than anywhere: nobody reads a chore before it is committed. Use chores
  for changes your checks genuinely cover, and read the diff before merging.
- Behaviour-changing fixes are out of scope by instruction ("if the fix would change what the code does for a
  caller, answer BLOCKED"), not by proof. The size caps and the locked tests are what actually hold.
- A finder whose output depends on line numbers only (two identical findings in one file) is treated as one kind
  of finding per file: fixing either counts.
