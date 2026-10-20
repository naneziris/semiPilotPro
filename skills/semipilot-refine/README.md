# semipilot-refine

Turns a rough feature idea into a precise, testable `requirements.md`: problem, scope, impact analysis, and
acceptance criteria that each name the automated check proving them (`[check: test_csv_has_header]`).

Part of the [semiPilot](https://github.com/naneziris/semiPilotPro) suite, and useful on its own: a spec written
this way is easy to review, easy to plan, and tells a coding agent exactly when it is done.

## Use

In your agent's chat:

```
/semipilot-refine let shop admins export the orders list as CSV
```

or just describe the feature and ask for requirements — the skill triggers on its description.

It proposes a slug, asks at most five questions, does the impact analysis first, and writes
`.semipilot/features/<slug>/requirements.md` with `status: draft`. Next step: `semipilot-spec-critic`.

## What it needs

Nothing but the repository. If the repository has a semiPilot knowledge layer (`docs/cards/` + `scripts/kb/kb.py`),
the skill uses it for deterministic retrieval and runs `python3 scripts/kb/kb.py` (read-only). Otherwise it reads
your instructions files and the code.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | The process the agent follows |
| `references/requirements-template.md` | The exact structure of `requirements.md` |
| `references/acceptance-criteria.md` | How to write tagged, observable criteria (good/bad table, checklist) |
| `examples/idea.md`, `examples/requirements.md` | A worked example, input to output |

## Compatibility

Open Agent Skills format (`SKILL.md` + `references/` + `examples/`). Targets GitHub Copilot (VS Code chat, Copilot
CLI) and Claude Code; any harness that reads Agent Skills can load it. `argument-hint` is used by Copilot and Claude
Code and ignored elsewhere.

## Safety

Writes one file inside `.semipilot/features/<slug>/`. Runs no commands except the read-only knowledge-layer
validator and resolver when that layer exists. No network access.

License: MIT.
