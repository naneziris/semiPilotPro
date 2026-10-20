# semipilot-scribe

Keeps a codebase's knowledge layer true after each feature: applies exactly the *Knowledge Updates Required* the
semiPilot planner listed — module cards, area instructions, ADRs, dependency policy, changelog — then runs the
deterministic checks (`kb validate`, `kb index`, `kb guard`, `kb drift`) and reports gaps instead of guessing.

## Use

After reviewing a feature's diff:

```
/semipilot-scribe export-orders-csv
```

## Requires

A semiPilot knowledge layer in the repository (`docs/cards/` and `scripts/kb/kb.py`, installed with
`semipilot kb init` — see the `semipilot-knowledge` skill), and `python3`. Knowledge layers installed before v0.2
(Node scripts) keep working.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | The work-list-driven process and its hard constraints |
| `references/card-format.md` | The card schema and every validation error with its fix |
| `references/adr-and-changelog.md` | ADR and changelog formats |
| `examples/scribe-report.md` | A work list, the surgical card edit, and the report |

## Safety

Edits only knowledge files listed in the plan (`docs/cards/`, `docs/*.md`, `.github/instructions/`). Never touches
code. Runs only `kb` commands (read-only, except `kb index`, which rewrites `docs/cards/manifest.json`) and
`git diff`. No network access.

License: MIT.
