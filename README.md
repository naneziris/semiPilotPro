# semiPilot

**Human-gated, test-first agentic development for GitHub Copilot and Claude Code.**

You write down what you want, a critic checks it, you approve it — and an unattended loop plans the work, writes
locked tests first, implements one small task at a time in a fresh agent process, runs *your* checks after every
attempt, has a read-only reviewer grade the result, and leaves you a branch, a review packet and a list of every
assumption it made. It never weakens a test, never wanders outside its task, never pushes on its own, and stops the
moment it would have to guess — or the moment the feature's **risk tier** says a person should look.

```
 issue ─ semipilot intake ─┐
                           ▼
 you + agent chat                          semipilot CLI (unattended)                              you
┌─────────────────────┐   approve   ┌───────────────────────────────────────────────────────┐   ┌───────────────┐
│ /semipilot-refine   │────────────▶│ plan → 2 critic gates ─●─ locked tests (red first)    │──▶│ review packet │
│ /semipilot-spec-    │  (Gate 1)   │ → T1 ─○─ T2 ─○─ … Tn → full suite → reviewer (rubric) │   │ scribe        │
│        critic       │             │ each task: fresh agent → scope/lock/diff → your checks│   │ semipilot mr  │
└─────────────────────┘             └───────────────────────────────────────────────────────┘   └───────────────┘
   requirements.md (risk: …)          ● medium + high risk: you approve the plan     ○ high risk: you read each task
```

Separately, `semipilot chore` makes **one small fix per run** (a lint finding, an anti-pattern) with nobody
watching, and keeps it only if a purely mechanical gate passes — the kind of loop that has earned running alone.

| | |
|---|---|
| **Runs on** | GitHub Copilot CLI or Claude Code (headless), chosen per project |
| **Autonomy** | Per feature: `risk: low \| medium \| high` decides where the run stops for a human; the plan's paths can raise it |
| **Chat front-end** | Five [Agent Skills](https://agentskills.io) for VS Code Copilot chat, Copilot CLI and Claude Code |
| **Knowledge layer** | Optional: module cards + a closed vocabulary + `kb.py` — deterministic retrieval instead of grep |
| **Install** | `pipx`, or a plain download with no pip at all |
| **License** | MIT |

## Why

Better models don't fix missing information. Wrong assumptions at the requirements level compound into a large,
coherent, wrong diff; implementation mistakes are cheap and self-correct in a loop. So semiPilot keeps the human at
the **front** (intent, acceptance criteria, approval) and the **back** (review), and takes them out of the middle —
where a loop with hard guardrails does better than a tired human nodding plans through.

Generation is cheap; a person's attention is not. So how far a loop may run alone depends on what can be verified
cheaply: a small fix your checks fully cover can run unattended (`chore`), an ordinary feature runs to the end and is
reviewed once (`low`), a design decision is read before it is built (`medium`), and auth, money and migrations are
read task by task (`high`). And the review itself is prepared: the report opens with what to read first and the
evidence per acceptance criterion. See [docs/autonomy.md](docs/autonomy.md).

## Quick start

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v6
cd your-repo
semipilot init --harness claude      # or: --harness copilot   (installs the skills where that agent finds them)
semipilot doctor                     # tells you what is still missing
```

Then, per feature:

1. **Refine** — in your agent's chat: `/semipilot-refine let admins export orders as CSV` (or start from an issue:
   `semipilot intake 12`, then `/semipilot-refine <slug>`). It asks at most five questions and writes
   `.semipilot/features/<feature>/requirements.md`: every acceptance criterion tagged with the check that proves it,
   and a proposed risk tier.
2. **Gate 1** — `/semipilot-spec-critic`, then reply `approve`.
3. **Run** — in a terminal tab of your own (not inside an agent chat), on your base branch: `semipilot run <feature>`.
   It asks the planner's questions first (answer them inline, run again), then builds on `feat/<feature>`.
   At `medium` or `high` risk it stops for you: read `implementation-plan.md`, then `semipilot approve <feature>`
   (at `high` also `semipilot resume <feature>` after each task). Interrupted? `semipilot resume <feature>` —
   never `run` again.
4. **Review** — `semipilot review <feature>`: the review packet (what to read first, evidence per criterion, the
   reviewer's rubric), then assumptions, blocked tasks, checks, warnings.
   Wrong assumption → `semipilot rollback <feature> T3`, fix the spec, `semipilot resume <feature>`.
5. **Ship** — when you have read the diff: `semipilot mr <feature>` pushes the branch and opens a draft request whose
   description is built from the packet.

| Step | Where |
|---|---|
| refine, spec critic, scribe | your agent's chat (`/semipilot-…`) |
| `preflight`, `status`, `review`, `rollback`, `intake`, `mr` | chat or terminal |
| `run`, `resume`, `approve`, `replan`, `chore` | **a plain terminal tab** — they run for a long time and start their own agents |

Full walkthrough: **[docs/getting-started.md](docs/getting-started.md)**.

No pip on the machine? Download the branch as a ZIP, unzip, and run `bin/semipilot` (or `bin\semipilot.cmd`) —
details in [getting started](docs/getting-started.md#install-without-pip).

## What it guarantees

Verified by the orchestrator after every agent call, or built into the command line — not requested in a prompt:

- **Fresh session per call.** Resume/session flags are refused; so are flags that bypass permission rules.
- **Least privilege per role.** Planner and critics get read-only tools; test-writer and implementer can edit and run
  commands. A deny list in each harness's own permission rules blocks `git push`, `commit`, `reset`, branch
  switching, package installs and web tools. It matches command prefixes — a seatbelt, not a sandbox
  ([details](docs/harnesses.md#permissions), [SECURITY.md](SECURITY.md)) — so the checks below verify the effect.
- **The run branch stays checked out.** An agent that switches branches halts the run; no reset ever touches another
  branch.
- **Tests are locked before code exists — and must fail first.** A changed locked test is reverted and the attempt
  counted; a test that passes before the implementation exists is flagged for you (or halts the run).
- **A person looks where the tier says so.** `medium` and `high` features cannot get past the plan without
  `semipilot approve`; `high` cannot start the next task without `semipilot resume`. A plan touching a sensitive
  path raises the tier by itself.
- **Scope and size.** Files outside the task, files owned by another task, and oversized diffs are reverted or block
  the task.
- **Done means your checks pass** — lint, typecheck, tests, build, as configured — never the agent's opinion.
- **No silent guesses.** Ambiguity becomes a logged, reversible decision (`decisions.md`) or a `BLOCKED:` question.
- **Outages are not failures.** Transient errors back off and retry without blaming the task; auth and quota halt
  immediately; a circuit breaker stops a long outage; `resume` continues where it stopped.
- **Agents never push.** `git push` is denied to every role. A branch leaves the machine only through
  `semipilot mr` (or the two settings that ask for it), and then the program pushes, not an agent.
- **The reviewer cannot change anything and cannot approve anything.** Read-only, checked after the call; its
  verdict opens the report as advice.

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, set up a project, build the first feature |
| [Concepts](docs/concepts.md) | The flow, the gates, the artifacts, the guarantees, and when not to use it |
| [Autonomy](docs/autonomy.md) | Risk tiers, plan approval and per-task review, the red check, the reviewer agent, the review packet |
| [Chores](docs/chores.md) | One small unattended fix per run: setup, the gate, scheduling |
| [Issues and merge requests](docs/forge.md) | `semipilot intake` and `semipilot mr` with `gh` / `glab` |
| [Harnesses](docs/harnesses.md) | Copilot CLI vs Claude Code: setup, permissions, errors, cost, switching |
| [Skills](docs/skills.md) | The five skills, how each harness loads them, plugin install |
| [Knowledge layer](docs/knowledge-layer.md) | Cards, vocabulary, `kb.py`, bootstrap, enforcement |
| [Configuration](docs/configuration.md) | Every key in `.semipilot/config.yaml` |
| [CLI reference](docs/cli.md) | Every command, flag and exit code |
| [Architecture](docs/architecture.md) | How the engine works, and how to add a harness |
| [Troubleshooting](docs/troubleshooting.md) | Common failures and what to do |
| [Upgrading](docs/upgrading.md) | What changed in 0.3 (v6) and 0.2 (v5), and how to migrate |
| [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) | |

## Honest limits

- **Your tests are the ceiling.** The definition of done is "your checks pass". Weak tests produce confidently
  wrong code. Use the loop for well-specified features in areas with a real test suite.
- **Error strings drift.** Failure classification matches each CLI's error text by regex. Claude Code's patterns
  come from its documented messages; Copilot CLI's are seeded and not verified against every version. Calls
  classified `unknown` are logged — add their signature to `failure_patterns` ([how](docs/troubleshooting.md)).
- **A reviewer agent is not a review.** It shares the blind spots of the agents whose work it grades. It makes
  your reading faster; it does not replace it. If nobody reads what the loop builds, nobody understands the system
  a few months on — with the tests green the whole way.
- **Cost is real.** Every loop call starts a full agent session. The report shows calls and minutes per role, plus
  what the CLI reports: dollars on Claude Code; premium requests and tokens on Copilot CLI, read from its session
  files — that reading has not been verified against a live Copilot CLI yet ([configuration](docs/configuration.md#cost)).
  Budgets cap iterations, wall-clock time and, optionally, spend.
- **`intake` and `mr` are tested against a fake `gh`/`glab`**, not a live forge. Use `--dry-run` first.
- **Go and `make`-based projects** run the whole test set for every task (no per-file scoping) — slower, still works.

## Repository layout

```
src/semipilot/          the CLI and the orchestrator (harness.py = the adapters; roles/ = the loop's role prompts;
                        risk.py, review.py, usage.py, forge.py, chore.py = the 0.3 additions)
skills/                 the Agent Skills pack (single source of truth; packaged into the wheel)
.claude-plugin/         plugin manifests, so the skills can be installed as a plugin (Claude Code and Copilot CLI)
bin/                    launchers for running from a download (no pip)
tests/                  the orchestrator suite runs once per harness against a fake agent CLI; forge tests use a
                        fake gh/glab and a local bare remote
docs/                   documentation; docs/design/ holds the design records
```

The previous, step-by-step manual pipeline is on the `v3` branch; `v4` is the first CLI-only version; `v5` made it
harness-neutral; `v6` (this branch, 0.3) adds risk tiers, the review gate, cost reporting, chores and the forge
commands. Why: [docs/design/v6-loops-and-factories.md](docs/design/v6-loops-and-factories.md).
