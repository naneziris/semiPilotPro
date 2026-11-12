---
name: semipilot-run
description: "Operates semiPilot's unattended build loop (PilotInLoop) through the semipilot CLI — preflight and the planner's questions, starting a run, the plan-approval and per-task gates of medium/high-risk features, status, reading the review packet and report, rollback, resume, opening the merge request, issue intake and chores. Use when the user wants to build, run, preflight, approve, resume, roll back or review an approved semiPilot feature, asks 'what did the loop do', 'why did the run stop', 'what should I read first', 'open the MR', or 'semipilot status'."
license: MIT
compatibility: "Needs the semipilot CLI (pipx install, or the download with bin/ on PATH), git, and the GitHub Copilot CLI or Claude Code logged in."
argument-hint: "preflight|run|status|review|approve|replan|resume|rollback|mr <feature> [task]"
metadata:
  author: Nikos Aneziris
  version: "0.3.0"
  suite: semipilot
---

# semiPilot — operate the loop

The loop (PilotInLoop) turns an **approved** `requirements.md` into a branch of tested commits without a human in
the middle: plan → two critic gates → locked tests first (which must fail before the code exists) → one fresh agent
process per task → your checks after every attempt → a read-only reviewer → report. How much of that is unattended
depends on the feature's **risk tier** (`risk:` in its requirements): `low` runs straight through, `medium` stops
once for the human to approve the plan, `high` also stops after every task. You help the user drive it from chat.
The CLI does the work; you run its commands, read its files, and explain what happened.

Your most useful job is at the end: the human's review is the one step that does not scale, so make it short and
sharp. Lead them through the review packet; never tell them it looks fine so they can skip reading.

Check the CLI first: `semipilot --version`. Missing → tell the user how to install it (README of semiPilot:
`pipx install git+https://github.com/naneziris/semiPilotPro.git@v6`, or download and run `bin/semipilot`) and stop.

## Commands you may run

| Command | When | Duration |
|---|---|---|
| `semipilot status` | Where every feature stands | seconds |
| `semipilot doctor` | Setup problems (checks, CLI login, knowledge layer) | seconds–1 min |
| `semipilot preflight <feature>` | Approved spec → checks + the planner's questions | 1–5 min — run it with a long command timeout (≥ 10 min); if your tool cannot wait that long, hand it to the user like `run` |
| `semipilot review <feature>` | After a run: prints `report.md`, the review packet first | seconds |
| `semipilot rollback <feature> <task>` | A wrong assumption in task T*n*, or a task the user rejects at its review — **ask the user first** | seconds |
| `semipilot approve <feature> --no-run` | The user read `implementation-plan.md` and **said** they approve it | seconds |
| `semipilot replan <feature> -m "<their words>" --no-run` | The user wants the plan changed; pass what they said, unedited | seconds |
| `semipilot mr <feature> --dry-run` | Show what the merge request would be | seconds |
| `semipilot mr <feature>` | Push the run branch and open a draft request — **only when the user asks for exactly that** | seconds |
| `semipilot intake <issue>` | The user wants to start from a GitHub/GitLab issue; then `/semipilot-refine <slug>` | seconds |
| `semipilot chore --list` / `--dry-run` / `--history` | What the chores would fix, and what they did | seconds |

## Commands you hand to the user instead of running

`semipilot run <feature>`, `semipilot resume <feature>` and `semipilot chore` (and `approve` / `replan` without
`--no-run`, which continue the run) take minutes to hours and start their own agent processes. **Never run them yourself** — not here, not detached, not in a new or "separate" terminal you open: your
shell tool times out long commands, a detached process dies with this session, and a run started by an agent is
retried and diagnosed by that agent at the user's expense. The user runs them in a terminal tab **they** open, in the
project folder. Give them exactly this, filled in, and stop:

```bash
git checkout main            # the run branches off the branch you are on
semipilot run <feature>      # macOS: caffeinate -i semipilot run <feature>
```

If the user insists on starting it from this chat, run it in the foreground in the current shell with the longest
timeout your tool allows, and say once that a plain terminal tab is more reliable. Never `nohup` or background it.

**After any interruption the command is `semipilot resume <feature>`, never `run` again** — the run branch and its
checkpoint already exist, and `resume` switches to the branch itself. `run` says so too if it is used by mistake.

## Where each step happens

| Step | Where | Who |
|---|---|---|
| `/semipilot-refine`, `/semipilot-spec-critic` → `approve` | agent chat | user + you |
| `semipilot preflight <feature>`, answering `open-questions.md` | chat or terminal | you may run it; the user answers |
| `semipilot run` / `semipilot resume` | **the user's own terminal tab** | user |
| reading `implementation-plan.md` at a plan-approval stop; `approve` / `replan` | chat + terminal | the user decides; you explain the plan |
| reading a task's commit at a per-task stop; `resume` / `rollback` | chat + terminal | the user decides; you explain the commit |
| `semipilot status` / `review` / `rollback` | chat or terminal | you may run them |
| `semipilot mr <feature>` | chat or terminal, after the review | the user asks; you may run it |
| `/semipilot-scribe <feature>` | agent chat, after the user reviewed the diff | user + you |

## Flow

1. **Preflight.** Run `semipilot preflight <feature>`. It refuses with a clear reason when something is wrong
   (unapproved spec, untagged criteria, dirty tree, an earlier run of the feature, knowledge layer unhealthy, agent
   CLI not installed) — relay the reason and the fix it prints; do not improvise another one.
2. **Questions.** When it writes `.semipilot/features/<feature>/open-questions.md`, help the user answer each
   `Answer:` line. Never answer for them; you may explain each question and its recommended default. Re-run
   preflight until it prints *Ready*.
3. **Run.** Hand over the run command (above) and stop. The user comes back when it has stopped; every stop prints
   `Stopped: <what happened>` (or `Your turn: …` at a risk tier's gate) and `Next: <command>`.
4. **Plan approval** (`plan_approval`, medium and high risk). Open `implementation-plan.md` with the user. Say in a
   few lines what will be built, in which files, in what order, and name the decisions that will be hard to change
   later (a new interface, a schema, a dependency between modules) — those are what this stop is for. Do not
   recommend approval; ask what they think. They approve → `semipilot approve <feature> --no-run`, then hand them
   `semipilot resume <feature>`. They want changes → `semipilot replan <feature> -m "<their words>" --no-run`, then
   `resume`: the planner gets their words above the critics', and the new plan stops for approval again.
5. **Task review** (`task_review`, high risk). The stop names the commit. Show `git show <sha>` and the task's
   locked test; explain what changed and what the test proves. Accept → the user runs `semipilot resume <feature>`.
   Reject → `semipilot rollback <feature> <task>` (ask first), fix the requirements, then `resume`.
6. **Review.** After the run: `semipilot review <feature>`, then walk the user through the report in the order of
   [references/reading-the-report.md](references/reading-the-report.md): the review packet's *Read first* list, the
   evidence table, then assumptions, blocked tasks, and the commits in the packet's reading order.
7. **Decide.** Use [references/stop-reasons.md](references/stop-reasons.md) to explain why the run stopped and the
   next action: fix the spec and `resume`, `rollback` a task built on a wrong assumption, answer a `BLOCKED:`
   question, or — when the user has read the diff and is happy — run the `semipilot-scribe` skill if the repository
   has a knowledge layer, and then `semipilot mr <feature>` when they ask for the request to be opened.

## Hard constraints

- Do not check connectivity, logins or GitHub yourself (no `curl`, `ping`, `gh auth`, `copilot` test calls). The CLI
  reports login, quota and outage problems itself, with the fix — relay its message. `semipilot doctor --live` is the
  only check, and only when the user asks for it (it costs one model call).

- Never push, merge or delete a branch yourself. The only way a branch leaves the machine is `semipilot mr`, and
  you run it only when the user asks for the request to be opened — never because a run completed.
- Never run `semipilot approve` or accept a task for the user. Those gates exist so that a person looks; "the plan
  seems fine to me" is not their approval.
- The reviewer agent's verdict is advice. Report it as what an agent thinks, show where it points, and never use
  it as a reason the user need not read the diff.
- Never edit locked tests, `requirements.md` (except when the user asks you to fix it after a rollback), cards or
  instructions files while operating the loop.
- `rollback` adds revert commits to the run branch and resets those tasks to pending: confirm with the user first.
- Report what the files say. If the report and the diff disagree, say so — do not smooth it over.
