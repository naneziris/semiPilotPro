# semipilot-run

Drive semiPilot's unattended build loop (PilotInLoop) from your agent's chat: preflight and the planner's
questions, the run command, status, the report walk-through, rollback and resume — with the rules that keep it
safe (the long run is handed to you for a terminal tab of your own — the agent never starts it; rollback is confirmed first; nothing is ever pushed).

## Use

```
/semipilot-run preflight export-orders-csv
/semipilot-run review export-orders-csv
```

or ask "why did the run stop?" — the skill triggers on its description.

## Requires

The `semipilot` CLI (this repository), git, and the agent CLI the loop runs on (GitHub Copilot CLI or Claude Code),
logged in. This skill is the chat front-end; the CLI does the work.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Which commands the agent runs, which it hands to you, the flow |
| `references/reading-the-report.md` | The report section by section, in order of risk |
| `references/stop-reasons.md` | Every stop reason and the next action |
| `examples/session.md` | A full preflight → run → review conversation |

## Safety

Runs only `semipilot status|doctor|preflight|review` on its own; `rollback` only after you confirm; `run`/`resume`
are handed to you to run in a terminal tab of your own — the agent never starts them. Never pushes, merges or opens PRs.

License: MIT.
