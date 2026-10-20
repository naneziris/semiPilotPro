# semipilot-spec-critic

Gate 1 of semiPilot: a rigorous review of a `requirements.md` before anyone builds it. Seven checks — observable
tagged criteria, coverage, feasibility against the data model and architecture, a real impact analysis, edge
cases, open questions with defaults, size — and one verdict: `APPROVED` or `REJECTED` with the single most
important fix first. On the user's explicit `approve`, it records `status: approved`, which is what lets the
unattended loop run.

Part of the [semiPilot](https://github.com/naneziris/semiPilotPro) suite; works on any `requirements.md` that
follows the `semipilot-refine` structure.

## Use

```
/semipilot-spec-critic export-orders-csv
…  ### SPEC-CRITIC: APPROVED …
approve
```

No slug → it reviews the most recently modified draft and says which one.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Process, output format, approval rule |
| `references/gate1-checklist.md` | The seven checks with reject conditions — and what is *not* a reason to reject |
| `examples/rejected.md`, `examples/approved.md` | Verdicts as the agent should write them, including the approval diff |

## Compatibility

Open Agent Skills format. Targets GitHub Copilot (VS Code chat, Copilot CLI) and Claude Code; any harness that
reads Agent Skills can load it.

## Safety

Read-only except for one line (`status:`) in the reviewed file, and only after the user's explicit yes. Runs the
read-only knowledge-layer validator/resolver when present. No network access.

License: MIT.
