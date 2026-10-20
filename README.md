# semiPilot

**Human-gated, test-first agentic development for GitHub Copilot and Claude Code.**

You write down what you want, a critic checks it, you approve it — and an unattended loop plans the work, writes
locked tests first, implements one small task at a time in a fresh agent process, runs *your* checks after every
attempt, and leaves you a branch, a report and a list of every assumption it made. It never pushes, never weakens a
test, never wanders outside its task, and stops the moment it would have to guess.

```
 you + agent chat                          semipilot CLI (unattended)                         you
┌─────────────────────┐   approve   ┌──────────────────────────────────────────────────┐   ┌──────────────┐
│ /semipilot-refine   │────────────▶│ plan → 2 critic gates → locked tests → T1 … Tn   │──▶│ review report│
│ /semipilot-spec-    │  (Gate 1)   │ each task: fresh agent → scope/lock/diff checks  │   │ scribe → PR  │
│        critic       │             │            → your checks → commit or retry/block │   └──────────────┘
└─────────────────────┘             └──────────────────────────────────────────────────┘
        requirements.md                     feat/<feature> branch · report.md · decisions.md
```

| | |
|---|---|
| **Runs on** | GitHub Copilot CLI or Claude Code (headless), chosen per project |
| **Chat front-end** | Five [Agent Skills](https://agentskills.io) for VS Code Copilot chat, Copilot CLI and Claude Code |
| **Knowledge layer** | Optional: module cards + a closed vocabulary + `kb.py` — deterministic retrieval instead of grep |
| **Install** | `pipx`, or a plain download with no pip at all |
| **License** | MIT |

## Why

Better models don't fix missing information. Wrong assumptions at the requirements level compound into a large,
coherent, wrong diff; implementation mistakes are cheap and self-correct in a loop. So semiPilot keeps the human at
the **front** (intent, acceptance criteria, approval) and the **back** (review), and takes them out of the middle —
where a loop with hard guardrails does better than a tired human nodding plans through.

## Quick start

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v5
cd your-repo
semipilot init --harness claude      # or: --harness copilot   (installs the skills where that agent finds them)
semipilot doctor                     # tells you what is still missing
```

Then, per feature:

1. **Refine** — in your agent's chat: `/semipilot-refine let admins export orders as CSV`. It asks at most five
   questions and writes `.semipilot/features/<feature>/requirements.md`, every acceptance criterion tagged with the
   check that proves it.
2. **Gate 1** — `/semipilot-spec-critic`, then reply `approve`.
3. **Run** — in a terminal on your base branch: `semipilot run <feature>`. It asks the planner's questions first
   (answer them inline, run again), then builds on `feat/<feature>`.
4. **Review** — `semipilot review <feature>`: assumptions first, then blocked tasks, checks, warnings, a PR draft.
   Wrong assumption → `semipilot rollback <feature> T3`, fix the spec, `semipilot resume <feature>`.

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
- **Tests are locked before code exists.** A changed locked test is reverted and the attempt counted.
- **Scope and size.** Files outside the task, files owned by another task, and oversized diffs are reverted or block
  the task.
- **Done means your checks pass** — lint, typecheck, tests, build, as configured — never the agent's opinion.
- **No silent guesses.** Ambiguity becomes a logged, reversible decision (`decisions.md`) or a `BLOCKED:` question.
- **Outages are not failures.** Transient errors back off and retry without blaming the task; auth and quota halt
  immediately; a circuit breaker stops a long outage; `resume` continues where it stopped.

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, set up a project, build the first feature |
| [Concepts](docs/concepts.md) | The flow, the gates, the artifacts, the guarantees, and when not to use it |
| [Harnesses](docs/harnesses.md) | Copilot CLI vs Claude Code: setup, permissions, errors, cost, switching |
| [Skills](docs/skills.md) | The five skills, how each harness loads them, plugin install |
| [Knowledge layer](docs/knowledge-layer.md) | Cards, vocabulary, `kb.py`, bootstrap, enforcement |
| [Configuration](docs/configuration.md) | Every key in `.semipilot/config.yaml` |
| [CLI reference](docs/cli.md) | Every command, flag and exit code |
| [Architecture](docs/architecture.md) | How the engine works, and how to add a harness |
| [Troubleshooting](docs/troubleshooting.md) | Common failures and what to do |
| [Upgrading from v4](docs/upgrading.md) | What changed in 0.2 and how to migrate |
| [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) | |

## Honest limits

- **Your tests are the ceiling.** The definition of done is "your checks pass". Weak tests produce confidently
  wrong code. Use the loop for well-specified features in areas with a real test suite.
- **Error strings drift.** Failure classification matches each CLI's error text by regex. Claude Code's patterns
  come from its documented messages; Copilot CLI's are seeded and not verified against every version. Calls
  classified `unknown` are logged — add their signature to `failure_patterns` ([how](docs/troubleshooting.md)).
- **Cost is real.** Every loop call starts a full agent session. Claude Code reports cost per call (summed in the
  report); Copilot consumes premium requests. Budgets cap iterations and wall-clock time.
- **Go and `make`-based projects** run the whole test set for every task (no per-file scoping) — slower, still works.

## Repository layout

```
src/semipilot/          the CLI and the orchestrator (harness.py = the adapters; roles/ = the loop's role prompts)
skills/                 the Agent Skills pack (single source of truth; packaged into the wheel)
.claude-plugin/         plugin manifests, so the skills can be installed as a plugin (Claude Code and Copilot CLI)
bin/                    launchers for running from a download (no pip)
tests/                  245 tests; the orchestrator suite runs once per harness against a fake agent CLI
docs/                   documentation; docs/design/ holds the design records
```

The previous, step-by-step manual pipeline is on the `v3` branch; `v4` is the first CLI-only version.
