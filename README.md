# ai-ready-kit

Everything needed to make a repository AI-ready: a deterministic **knowledge
layer** (module cards + closed vocabulary + zero-dependency scripts that
retrieve, validate, and drift-check it), the **enforcement** that keeps it
true (pre-commit hook, CI workflow, Copilot instruction files), and
optionally the **SemiPilot pipeline** (requirements → two self-running critic gates →
plan → implement → scribe) rewired to run on that layer.

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

## The one rule that keeps it alive

Stale metadata is worse than none. Cards update in the same PR as the code
they describe — the guard nags, the scribe maintains, the hook and CI
enforce. When any agent says "the cards don't cover X", fix the cards; never
work around them.
