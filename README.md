# semipilot

The semiPilot pipeline as one installable tool: refine requirements, pass Gate 1, then let **PilotInLoop** plan,
write the tests first, implement task by task on GitHub Copilot CLI, and leave you a report and a branch to review.

You stay at the two places where judgment matters — the requirements and their approval at the front, the review at
the back. Everything in between is a loop that cannot push, cannot weaken a test, cannot wander outside its task,
and stops the moment it would have to guess. Same agents, same artifacts and same vocabulary as semiPilotPro
(`@refiner` → `requirements.md`, `@spec-critic`, `implementation-plan.md`, `decisions.md`, `@scribe`) — just
without the setup.

## Install

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v4   # PyPI: coming
```

Prerequisites: git, Python 3.9+, and the [GitHub Copilot CLI](https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli)
on your PATH and logged in (`copilot login`). VS Code with Copilot Chat for the two interactive steps.

### No pip / pipx? Install from a download

The tool is pure Python and bundles its one runtime dependency, so a plain copy of the files runs as-is.
Download the `v4` branch as a ZIP from GitHub (Code → Download ZIP, or
`https://github.com/naneziris/semiPilotPro/archive/refs/heads/v4.zip`), unzip it anywhere, and put its `bin/`
folder on your PATH:

```bash
unzip semiPilotPro-v4.zip && cd semiPilotPro-v4
export PATH="$PWD/bin:$PATH"        # or: ln -s "$PWD/bin/semipilot" ~/bin/semipilot
semipilot --version
```

On Windows, add the unzipped `bin\` folder to PATH (`bin\semipilot.cmd` finds Python via the `py` launcher or
`python`). Both launchers run `python -m semipilot` with `src/` on the path — nothing is installed and nothing is
written outside the folder, so removing the folder uninstalls it.

Copying only `src/semipilot/` also works: keep the folder whole (it carries the agents, prompts, `defaults.yaml`,
the plan schema and a bundled PyYAML in `_vendor/`), put it somewhere on the path, and run `python -m semipilot`
(the `semipilot` command itself comes from pip; without it use `python -m semipilot` or a launcher like `bin/`).
Without `jsonschema` (or with the 3.x version some OSes ship) the plan is validated by shape only; `pip`/`pipx`
installs get the full JSON-schema check.

## Use

**Once per repository**

```bash
cd your-repo
semipilot init        # detects your stack, writes .semipilot/config.yaml, the two chat prompts, the agents, an instructions template
semipilot doctor      # tells you what is still missing
```

Open `.semipilot/config.yaml` and confirm the `checks` (lint / typecheck / test / build). They define "done": a
task is only accepted when every check passes. Then fill in `.github/copilot-instructions.md` — one page of
commands, conventions and architecture that every agent reads first. If Copilot makes the same mistake twice, add a
line there. Have the semiPilotPro knowledge layer installed (`docs/cards/` + `scripts/kb/`)? `init` detects it and
everything below uses it — see *With the knowledge layer*.

**Per feature**

| Step | Where | What happens |
|---|---|---|
| `/refine-requirements export orders as CSV` | Copilot chat | `@refiner`: confirms tags (knowledge layer) or explores the code, asks at most five questions, writes `requirements.md` — problem, scope, impact analysis, acceptance criteria each tagged with the check that proves it (`[check: test_csv_has_header]`), assumptions, open questions. |
| `/spec-critic` | Copilot chat | Gate 1. Reviews coverage, testability, feasibility, edge cases, size. `APPROVED` or `REJECTED` with the required fix. On APPROVED you reply **approve** and it records `status: approved` — the one human gate before the loop. |
| `semipilot preflight export-orders-csv` | terminal | Checks (approved requirements, tags, clean tree, knowledge layer healthy, Copilot answers) and the planner's questions → `open-questions.md`. Answer them inline; run it again until it says *Ready*. |
| `semipilot run export-orders-csv` | terminal | PilotInLoop. Also does the preflight, so on a small feature you can skip `preflight`. |
| `semipilot review export-orders-csv` | terminal | The report: assumptions the loop made (read these first), blocked tasks, what got done, check results, a PR draft. |

Then act:

```bash
semipilot rollback export-orders-csv T3   # a wrong assumption: revert T3 and everything built on it
semipilot resume export-orders-csv        # continue after fixing the requirements, an outage, or a block
semipilot status                          # where every feature stands
```

The loop works on a branch `semipilot/<feature>-<date>` and never pushes. Review the diff, run `@scribe` if you have
the knowledge layer, open the PR yourself. Keep the machine awake for the run (`caffeinate -i semipilot run …` on
a Mac, or a server / dev container).

## What PilotInLoop does, unattended

1. **Plan.** `@pilotinloop-planner` turns the requirements into small tasks (≤ 5 files each) with explicit interfaces.
   The accepted plan is written as `implementation-plan.md` — tasks, files, test plan, interfaces, and a
   *Knowledge Updates Required* section for `@scribe`.
2. **Critique.** `@pilotinloop-spec-critic` (fidelity to the requirements) and `@pilotinloop-plan-critic`
   (conventions, contracts, sizing). Two rejected rounds halt the run rather than build the wrong thing;
   rejections go to `rejection-log.md`.
3. **Tests first.** One locked test file per task, written against the planned interfaces before any code exists.
   The implementer can add tests; it can never modify these.
4. **Implement.** One fresh Copilot process per task, with only that task, the requirements, the answers and the
   decisions log. After each attempt the orchestrator — not the agent — checks the test lock, the scope, the diff
   size, and runs your `checks`. Failure: retry with the failed diff still in the tree and the errors in the prompt.
   Same error twice: stop, mark the task blocked, move on.
5. **Report.** Full suite once at the end, then `report.md` and a state commit. Wherever the requirements were
   silent the loop chose the most reversible option and wrote it to `decisions.md`, or stopped with
   `BLOCKED: <question>`.

Copilot outages back off and retry without blaming the task; a long outage trips a breaker and `resume` picks up
where it stopped. Auth failures and quota exhaustion halt immediately.

## With the knowledge layer

If the repo has the semiPilotPro knowledge layer (`docs/cards/_vocabulary.md` and `scripts/kb/`), semipilot uses it
without configuration:

- `@refiner` validates it, proposes tags from the closed vocabulary, retrieves cards with `kb-resolve` and builds
  the impact analysis from the cards' `depends_on` / `public_contracts` / `invariants`; the tags land under
  *Knowledge References* in `requirements.md`.
- `@spec-critic` and the loop's planner, critics, test-writer and implementer all retrieve through `kb-resolve`
  with those tags and read only the resolved set; card invariants and contracts are hard constraints.
- `preflight` runs `kb-validate` and refuses to start on an unhealthy layer, like every other pipeline entry point.
- The planner emits `knowledge_updates` (cards, instructions, ADR, dependencies, changelog line), rendered into
  `implementation-plan.md` → *Knowledge Updates Required*, which is exactly what `@scribe` works from.
- The loop **never writes** to cards, instructions, ADRs or the changelog. After the run the flow is unchanged from the
  manual pipeline: review, `@scribe`, commit — the pre-commit hook and CI (`kb:guard`, `kb:drift`) stay the backstop.

Without it, the agents use `.github/copilot-instructions.md`, `AGENTS.md`, `.github/instructions/` and the code.
Force either way with `knowledge_layer: {mode: on|off}` in `.semipilot/config.yaml`.

## What it will never do

Push, merge, deploy, install packages, edit your instructions files or knowledge layer, weaken a test, resume a
Copilot session, or decide on its own that the work is done.

## Files it leaves in your repo

```
.semipilot/config.yaml                          the one file you edit
.semipilot/features/<feature>/                  requirements.md · open-questions.md · implementation-plan.md · plan.json
                                                decisions.md · rejection-log.md · report.md · implementation-progress.json
.semipilot/runs/                                per-call logs (git-ignored)
.github/prompts/refine-requirements.prompt.md   /refine-requirements
.github/prompts/spec-critic.prompt.md           /spec-critic
.github/agents/refiner.agent.md                 the two interactive agents …
.github/agents/spec-critic.agent.md
.github/agents/pilotinloop-*.agent.md           … and the three loop-only ones (planner, spec-critic, plan-critic)
.github/copilot-instructions.md                 yours — created only if missing
```

Coming from semiPilotPro? `init` never overwrites your files. An existing `@refiner` that writes to
`.github/requirements/requirements.md` keeps working: `semipilot run` uses that folder as-is when no per-feature
folder exists (`doctor` tells you; `semipilot init --force` swaps in the semipilot versions of the two agents).

Advanced: `semipilot config` prints the full effective configuration (budgets, guardrails, tool deny-list, failure
patterns); override any key in `.semipilot/config.yaml`. Put a file in `.semipilot/prompts/<name>.md` to override a
loop prompt (`planner-questions`, `planner-plan`, `spec-critic`, `plan-critic`, `test-writer`, `implementer`,
`test-fixer`).

## Honest limits

- The Copilot CLI's error strings for 5xx / 429 / 401 / quota are matched by regex (`failure_patterns`) and were
  not verified against every version. After your first real run, look for calls classified `unknown` in
  `.semipilot/runs/<run>/` and add their signature to the config.
- The loop's definition of done is "your checks pass". Weak tests produce confidently wrong code. Use it for
  well-specified features in areas with a real test suite; use the manual pipeline for the rest.
- Go and `make`-based repos run the whole test set per task (no per-file scoping). It works, it is just slower.

## How this maps to the AI-native SDLC playbook

Plan + Design → `requirements.md` (agent-drafted with the human, critic-reviewed, human-approved). Build →
`implementation-plan.md` + tasks, executed by the loop. Test → locked tests written first, continuous checks, a
full-suite verification at the end. Deploy → a branch and a PR draft; humans and your existing PR review own the
gate. Maintain → `@scribe` keeps the knowledge layer true; a monitoring hook that files a new `requirements.md`
from a production signal would close the loop and is not in scope yet.

## Developing

```bash
git clone … && cd semipilot
pip install -e ".[dev]"
pytest -q                 # 65 tests against a fake Copilot CLI (outages, quota, lock violations, rollbacks, knowledge layer, legacy layout …)
```

## Repository layout

```
src/semipilot/                       the CLI and the PilotInLoop orchestrator (_vendor/: bundled PyYAML for pip-less use)
bin/                                 launchers to run from a plain download (semipilot, semipilot.cmd)
tests/                               its test suite (fake Copilot CLI)
GETTING-STARTED.md                   knowledge layer install + the per-feature flow, on one page
docs/pilotinloop-handoff-v2.md       design of record for the loop (why it is built the way it is)
docs/copilot-cli-findings.md         what the Copilot CLI verifiably supports headless, and what is still unverified
```

The knowledge layer lives in its own repository (`semipilot-knowledge-layer`); the step-by-step manual pipeline of
earlier versions is on the `v3` branch.

Install from this repository until it is on PyPI:

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v4
```

No pip on the machine? See *No pip / pipx? Install from a download* under Install above.
