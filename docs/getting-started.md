# Getting started

From nothing to a reviewed feature branch. Allow 15 minutes for setup, then the per-feature flow.

## Prerequisites

- **git** and **Python 3.9+**
- **One agent CLI for the loop**, logged in:
  - GitHub Copilot CLI — `copilot`, then `copilot login` ([install](https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli)), or
  - Claude Code — `claude`, then `/login` once ([install](https://code.claude.com/docs))
- **A chat for the two interactive steps**: VS Code Copilot chat, Copilot CLI, or Claude Code — any of them can use
  the skill pack.
- A project with an automated test suite. The loop is only as good as your checks.

## Install

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v5
semipilot --version
```

### Install without pip

The tool is pure Python and bundles its one runtime dependency, so a plain copy of the files runs as-is:

1. Download the `v5` branch as a ZIP (GitHub → Code → Download ZIP, or
   `https://github.com/naneziris/semiPilotPro/archive/refs/heads/v5.zip`) and unzip it anywhere. Keep the folder
   whole: `bin/`, `src/` and `skills/` belong together.
2. Run `bin/semipilot` (macOS/Linux) or `bin\semipilot.cmd` (Windows). Put `bin/` on your PATH if you can. If you
   cannot change PATH, call the launcher by its full path (`~/tools/semiPilotPro-v5/bin/semipilot doctor`) or add a
   shell alias (`alias semipilot=~/tools/semiPilotPro-v5/bin/semipilot`).

Nothing is installed and nothing is written outside the folder; deleting the folder uninstalls it. Without the
`jsonschema` package the plan is validated by shape only; pip/pipx installs get the full JSON-schema check.

## Set up a project

```bash
cd your-repo
semipilot init --harness claude        # or --harness copilot
```

`--harness` picks the agent CLI that runs the unattended loop. Without it, `init` keeps the harness already in
`.semipilot/config.yaml`, else picks the only agent CLI on your PATH, else `copilot`.

`init` writes, and never overwrites:

| File | What it is |
|---|---|
| `.semipilot/config.yaml` | The one file you edit: `harness`, the `checks` that define done (detected from your stack), test patterns |
| `.semipilot/.gitignore` | Keeps per-call logs out of git |
| `.claude/skills/semipilot-*/` or `.agents/skills/semipilot-*/` | The [skill pack](skills.md), where your chat finds it |
| `AGENTS.md` | One page of instructions every agent reads first — only created if you have no instructions file yet |

Use `--skills both` when your team uses both chats (Copilot users and Claude Code users on one repository).

**Project in a subfolder of a monorepo?** `cd` into it and run `semipilot init --here`. Every later command finds the
project from anywhere inside it; branches and commits still go to the repository. The skills land in the subfolder's
`.agents/skills/` / `.claude/skills/`: open your chat in that folder (or copy the skills to the repository root's
skill folder, or to your personal one) so it finds them.

**Trialling it in a team repository first?** `semipilot init --private`: nothing semipilot writes is ever
committed, and `.github/` (your local agent and instruction changes) stays local too. Add other uncommitted files
you want to keep, such as your own package.json tweaks, under `git.local_paths`. See [configuration.md](configuration.md#private-and-gitlocal_paths--keep-files-out-of-git).

### Finish the setup

1. **Confirm the checks** in `.semipilot/config.yaml`. They define "done": a task is accepted only when every check
   passes. Keep `{task_tests}` in the test command — it expands to the current task's locked test files.
2. **Fill in `AGENTS.md`** (or your existing `.github/copilot-instructions.md` / `CLAUDE.md`): commands,
   conventions, architecture, invariants — one page. The plan critic rejects every plan while it still holds
   `{{TODO}}` placeholders. When an agent makes the same mistake twice, add a line.
3. **Check:** `semipilot doctor` (add `--live` once to confirm the agent CLI is logged in; that costs one small
   call). It verifies the config, that the harness is installed, the skill pack, the
   instructions file, the checks, and the knowledge layer if you have one.

### Optional: the knowledge layer

```bash
semipilot kb init --system <prefix>      # e.g. shop → card ids like shop.billing
git config core.hooksPath .githooks      # once per clone — use the exact path kb init prints (subfolder projects differ)
```

Then, in your agent's chat, `/semipilot-knowledge bootstrap` — it inventories the repository and drafts the tag
vocabulary, the instructions and the module cards, stopping for your approval at every gate (½–2 days of review for
a real codebase). With a knowledge layer, every agent retrieves exactly the cards for a feature's tags instead of
searching the code. See [knowledge-layer.md](knowledge-layer.md).

## Build a feature

### 1. Refine

In your agent's chat:

```
/semipilot-refine let shop admins export the orders list as CSV
```

The refiner proposes a slug (`export-orders-csv`), confirms tags with you if there is a knowledge layer, asks at most
five questions, does an impact analysis, and writes `.semipilot/features/export-orders-csv/requirements.md`:
problem, scope, impact, acceptance criteria each ending in `[check: <test name>]`, assumptions, open questions.

### 2. Gate 1

```
/semipilot-spec-critic export-orders-csv
```

`REJECTED` → run `/semipilot-refine` again with the required fix. `APPROVED` → read the criteria once more and reply
`approve`; the critic records `status: approved`. This is the last cheap moment to fix a misread idea.

### 3. Preflight and the planner's questions

```bash
git checkout main
semipilot preflight export-orders-csv
```

It checks the spec (approved, every criterion tagged), the working tree (clean, branch name free), the knowledge
layer, and that the agent CLI is installed. Then the planner lists what it would otherwise have to guess in
`open-questions.md`. Fill in every `Answer:` line — copying the recommended default is fine — and run preflight again
until it says **Ready**. Five minutes here is the best-leveraged time of the whole run.

(`semipilot run` does the same preflight first, so for a small, clear feature you can skip this step.)

### 4. Run

```bash
semipilot run export-orders-csv            # macOS, keep it awake: caffeinate -i semipilot run export-orders-csv
```

The loop creates `feat/export-orders-csv` from the branch you are on and works unattended for minutes to hours:
plan → plan-fidelity critic and plan critic → locked tests → one task at a time → your checks → a commit per task → a final
full-suite run → the report. You do not need to watch it. It never pushes.

**Run it in a plain terminal tab you opened yourself** — not from inside Copilot CLI, Claude Code or VS Code chat.
The loop starts its own agent processes and runs for a long time; an agent's shell tool times it out, moves it to a
"background terminal" where it stalls, or retries it and spends your tokens diagnosing it. Running it inside an agent
session also does not show the run's cost: the loop's calls are separate processes. The cost is in the report
(Claude Code harness) and in your Copilot usage page (Copilot harness).

**If it stops or is interrupted** — closed laptop, killed terminal, outage — nothing is lost. Every stop prints
`Stopped: <what happened>` and `Next: <the command to run>`. For an interruption that is always:

```bash
semipilot resume export-orders-csv         # from any branch: it switches to the run branch itself
```

Do not `run` again: the run branch and its checkpoint already exist, and `run` will tell you to `resume`.

### 5. Review

```bash
semipilot review export-orders-csv
```

Read the report in order: **assumptions** (`decisions.md`) first, then blocked tasks, completed tasks, check results,
warnings. Then act:

| Situation | Do |
|---|---|
| A wrong assumption in T3 | `semipilot rollback export-orders-csv T3` (reverts T3 and everything built on it), fix `requirements.md`, `semipilot resume export-orders-csv` |
| A task is blocked with a question | Answer it in `requirements.md`, `semipilot resume …` |
| Interrupted (outage, budget, quota) or stopped with `BLOCKED:` | Fix the cause or answer in `requirements.md`, `semipilot resume …` — it continues at the stage that stopped |
| Happy | Review the diff, run `/semipilot-scribe export-orders-csv` if you have a knowledge layer, open the PR yourself |

The `semipilot-run` skill does this walk-through with you in chat: `/semipilot-run review export-orders-csv`.

`semipilot status` shows where every feature stands.

## Files semiPilot keeps in your repository

```
.semipilot/config.yaml
.semipilot/features/<feature>/
    requirements.md            yours (written with the refiner, approved by you)
    open-questions.md          the planner's questions and your answers
    implementation-plan.md     the accepted plan: tasks, files, interfaces, Knowledge Updates Required
    plan.json                  the same, machine-readable (kept outside the repo during the run)
    decisions.md               every assumption the loop made — read first
    rejection-log.md           what the critics rejected
    report.md                  the report
    implementation-progress.json   checkpoint for resume / rollback
.semipilot/runs/<run-id>/      one log per agent call: prompt, answer, output, classification (git-ignored)
```

Next: [concepts.md](concepts.md) for how and why it works this way.
