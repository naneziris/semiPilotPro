---
name: semipilot-run
description: "Operates semiPilot's unattended build loop (PilotInLoop) through the semipilot CLI — preflight and the planner's questions, starting a run, status, reading the report, rollback and resume. Use when the user wants to build, run, preflight, resume, roll back or review an approved semiPilot feature, asks 'what did the loop do', 'why did the run stop', or 'semipilot status'."
license: MIT
compatibility: "Needs the semipilot CLI (pipx install, or the download with bin/ on PATH), git, and the GitHub Copilot CLI or Claude Code logged in."
argument-hint: "preflight|run|status|review|resume|rollback <feature> [task]"
metadata:
  author: Nikos Aneziris
  version: "0.2.1"
  suite: semipilot
---

# semiPilot — operate the loop

The loop (PilotInLoop) turns an **approved** `requirements.md` into a branch of tested commits without a human in
the middle: plan → two critic gates → locked tests first → one fresh agent process per task → your checks after
every attempt → report. You help the user drive it from chat. The CLI does the work; you run its commands, read its
files, and explain what happened.

Check the CLI first: `semipilot --version`. Missing → tell the user how to install it (README of semiPilot:
`pipx install git+https://github.com/naneziris/semiPilotPro.git@v5`, or download and run `bin/semipilot`) and stop.

## Commands you may run

| Command | When | Duration |
|---|---|---|
| `semipilot status` | Where every feature stands | seconds |
| `semipilot doctor` | Setup problems (checks, CLI login, knowledge layer) | seconds–1 min |
| `semipilot preflight <feature>` | Approved spec → checks + the planner's questions | 1–5 min — run it with a long command timeout (≥ 10 min); if your tool cannot wait that long, hand it to the user like `run` |
| `semipilot review <feature>` | After a run: prints `report.md` | seconds |
| `semipilot rollback <feature> <task>` | A wrong assumption in task T*n* — **ask the user first** | seconds |

## Commands you hand to the user instead of running

`semipilot run <feature>` and `semipilot resume <feature>` take minutes to hours and start their own agent
processes. Do not run them inside this chat session (they would outlive it or block it). Give the user the exact
command for a separate terminal, on the base branch, on a machine that stays awake:

```bash
git checkout main            # the run branches off the branch you are on
semipilot run <feature>      # macOS: caffeinate -i semipilot run <feature>
```

If the user explicitly asks you to start it from here, start it detached with its output in a log file
(`nohup semipilot run <feature> > .semipilot/runs/<feature>.out 2>&1 &`) and tell them where the log is.

## Flow

1. **Preflight.** Run `semipilot preflight <feature>`. It refuses with a clear reason when something is wrong
   (unapproved spec, untagged criteria, dirty tree, branch exists, knowledge layer unhealthy, agent CLI not
   installed or not logged in) — relay the reason and the fix.
2. **Questions.** When it writes `.semipilot/features/<feature>/open-questions.md`, help the user answer each
   `Answer:` line. Never answer for them; you may explain each question and its recommended default. Re-run
   preflight until it prints *Ready*.
3. **Run.** Hand over the run command (above).
4. **Review.** After the run: `semipilot review <feature>`, then walk the user through the report in the order of
   [references/reading-the-report.md](references/reading-the-report.md): assumptions first, then blocked tasks,
   then completed tasks and checks, then warnings.
5. **Decide.** Use [references/stop-reasons.md](references/stop-reasons.md) to explain why the run stopped and the
   next action: fix the spec and `resume`, `rollback` a task built on a wrong assumption, answer a `BLOCKED:`
   question, or — when the user is happy — review the diff, run the `semipilot-scribe` skill if the repository has a
   knowledge layer, and open the PR themselves.

## Hard constraints

- Never push, merge, open a PR, or delete a branch. The loop never does; neither do you.
- Never edit locked tests, `requirements.md` (except when the user asks you to fix it after a rollback), cards or
  instructions files while operating the loop.
- `rollback` adds revert commits to the run branch and resets those tasks to pending: confirm with the user first.
- Report what the files say. If the report and the diff disagree, say so — do not smooth it over.
