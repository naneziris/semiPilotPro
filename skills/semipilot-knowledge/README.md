# semipilot-knowledge

A deterministic knowledge layer for any codebase: one card per module, a closed tag vocabulary, and a single
standard-library Python tool (`scripts/kb.py`) that validates the cards, resolves tags to an exact reading list,
verifies declared dependencies against the real import graph (TypeScript/JavaScript and Python), and flags cards
made stale by code changes. Agents stop grepping and read a small, correct, reproducible set of files.

## Use

```
/semipilot-knowledge bootstrap            make this repository AI-ready (gated, ½–2 days of review)
/semipilot-knowledge impact <change>      which modules, contracts and invariants a change touches
/semipilot-knowledge new-card <module>    scaffold a card that validates
/semipilot-knowledge sync                 update cards after a change
/semipilot-knowledge catchup              cards teammates' changes made stale (zero tokens to detect)
/semipilot-knowledge agents-md            just a good AGENTS.md, no cards
```

The tool on its own:

```bash
python3 scripts/kb/kb.py validate | index [--check] | resolve --tags a,b | drift | guard | catchup [--mark]
```

## Install the layer into a repository

With the semipilot CLI: `semipilot kb init --system <prefix>` (copies `scripts/kb/kb.py`, the templates, a
pre-commit hook and a CI workflow; never overwrites your files). Without it: copy `scripts/kb.py` to
`scripts/kb/kb.py` and the files in `assets/templates/` to the locations listed in `references/bootstrap.md`, then
run the bootstrap workflow.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | What the layer is, the tool, and which workflow to run |
| `references/retrieval.md` | How tags become a reading list (L0–L3), and why it stays well-defined |
| `references/bootstrap.md`, `cartographer.md` | Building the layer with human gates; per-domain card drafting |
| `references/impact.md`, `new-card.md`, `sync-cards.md`, `catchup.md`, `agents-md.md` | Day-to-day workflows |
| `references/card-format.md` | The card schema and every validation error with its fix |
| `scripts/kb.py` | The tool: Python 3.9+, standard library and git only |
| `assets/templates/` | AGENTS.md, vocabulary, card, area rules, docs manual, ADRs, dependencies, changelog, hook, CI |
| `examples/` | A complete card and a resolve walk-through |

## Compatibility

Open Agent Skills format. Targets GitHub Copilot (VS Code chat, Copilot CLI) and Claude Code; the files it produces
(`AGENTS.md`, cards) are read by any agent.

## Safety

`kb.py` reads files under the project root and runs read-only `git` commands. It writes only
`docs/cards/manifest.json` (`index`) and `.git/kb-last-sync` (`catchup --mark`). No network access, no package
installs, no elevated permissions. The workflows edit only knowledge files (`docs/`, `AGENTS.md`,
`.github/instructions/`), with the user's approval at every gate.

License: MIT.
