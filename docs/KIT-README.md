# ai-ready-kit

Everything needed to make a repository AI-ready: a deterministic **knowledge
layer** (module cards + closed vocabulary + zero-dependency scripts that
retrieve, validate, and drift-check it), the **enforcement** that keeps it
true (pre-commit hook, CI workflow, Copilot instruction files), and
optionally the **SemiPilot pipeline** (requirements → two self-running critic gates →
plan → implement → scribe) rewired to run on that layer, and on top of that the
**PilotInLoop** — the same agents driven by a Python orchestrator that plans,
critiques, writes locked tests and implements a feature unattended, with the
human only at the front (refine + answer questions) and the back (morning review).

Extracted from a real production installation and generalized for any repo.
Read in this order: `INSTALL.md` (how to adopt), `USAGE.md` (the day-to-day
flow + what is scripted vs. AI and what costs tokens), `RETRIEVAL.md` (how
cards, the vocabulary, and the manifest turn tags into an exact reading list —
the progressive-disclosure mechanics), `PLAYBOOK.md` (the design reasoning). Adopting in a large workspace monorepo? `MONOREPO.md` is
the phased, size-proof rollout plan.

## Quick start

```bash
./install.sh /path/to/your-repo yourapp                  # knowledge layer only
./install.sh /path/to/your-repo yourapp --with-pipeline  # + SemiPilot pipeline
./install.sh /path/to/your-repo yourapp --with-pilotinloop # + pipeline + PilotInLoop
cd /path/to/your-repo
git config core.hooksPath .githooks
# then, in VS Code Copilot chat:
#   /bootstrap-knowledge-layer
```

The installer only copies files (never overwrites — safe to re-run); the
bootstrap prompt does the knowledge work with you approving every
knowledge-defining step. Budget ½–2 days per repo depending on size.

## What's in here

```
install.sh                     # mechanical installer (copy + {{SYSTEM}}/{{REPO_NAME}} substitution)
INSTALL.md                     # the adoption guide — read this
PLAYBOOK.md                    # the why: principles, artifact inventory, pitfalls
core/
  scripts/kb/                  # the 6 zero-dep scripts: validate, index(+check), resolve, drift, guard (+lib)
  githooks/pre-commit          # blocks commits on broken cards / stale manifest
  workflows/knowledge-layer.yml# CI: validate+check blocking, drift warning, guard nag
  vscode/settings.json         # chat.useAgentsMdFile
  prompts/                     # /impact, /new-card, /sync-cards
templates/                     # {{TODO}}-marked starting points the bootstrap fills:
                               # copilot-instructions, area instructions, AGENTS router block,
                               # vocabulary, card, docs/README (layer manual),
                               # decisions (ADRs), dependencies, CHANGELOG
pipeline/                      # optional: SemiPilot Pro patched for the knowledge layer
  agents/                      # refiner, spec-critic, planner, implementer, pattern-critic, scribe
  prompts/                     # run-pipeline, gate-triage, refine/plan/implement, fix-rejection, …
  skills/code-analyzer/        # complexity checks for the rail + Gate 2
  semipilot-core.md            # the machine contract
  INSTRUCTIONS.template.md     # the human manual (installed as INSTRUCTIONS.md)
  agents/pilotinloop-*.agent.md  # the 3 loop-only agents: planner (questions / plan.json), spec-critic, plan-critic
  PILOTINLOOP.template.md      # the runbook (installed as PILOTINLOOP.md): setup, evening, night, morning, troubleshooting
  pilotinloop/                   # optional: autonomous loop (installed as .github/pilotinloop/ + Makefile)
    orchestrator.py, runner.py # the loop + Copilot CLI runner (fresh process per task, guardrails, breaker)
    config.yaml                # checks, budgets, deny-list, failure patterns — everything tunable
    prompts/, tests/, Makefile # role prompts; 50-test suite with a fake Copilot CLI
docs/
  pilotinloop-handoff-v2.md      # design of record for PilotInLoop
  copilot-cli-findings.md      # what the Copilot CLI verifiably supports headless (and what is unverified)
bootstrap/
  bootstrap-knowledge-layer.prompt.md  # /bootstrap-knowledge-layer — AI-guided adoption with human gates
  cartographer.agent.md                # parallel card drafter for large repos
  generate-agents-md.prompt.md         # lightweight path: standalone AGENTS.md for a repo NOT getting the full kit
```

## Requirements & scope

- **Node ≥ 20** to run the kb scripts (they have zero npm dependencies).
- `kb-drift` analyzes **TypeScript/JavaScript** via the repo's own
  `typescript` package; configure layout in `scripts/kb/kb.config.json`.
  Other languages: everything else works — disable the drift CI job or swap
  in your own import extractor (one function).
- The hook/CI/prompts assume `npm run kb:*` aliases; the installer wires them
  into `package.json` when present, otherwise adjust to direct `node` calls.
- Pipeline layer targets **GitHub Copilot in VS Code** (`.agent.md`,
  `.prompt.md`, `applyTo` instruction files).
- PilotInLoop needs **Python ≥ 3.9** with `pyyaml` (+ `jsonschema` ≥ 4,
  `pytest` for its own tests), `make`, and the **Copilot CLI** on PATH,
  logged in. Its error classification is regex on CLI output and must be
  tuned after a first supervised dry run (`docs/copilot-cli-findings.md`).

## The one rule that keeps it alive

Stale metadata is worse than none. Cards update in the same PR as the code
they describe — the guard nags, the scribe maintains, the hook and CI
enforce. When any agent says "the cards don't cover X", fix the cards; never
work around them.
