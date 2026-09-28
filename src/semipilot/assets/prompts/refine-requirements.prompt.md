---
agent: refiner
description: semiPilot step 1 — turn a raw idea into a precise, testable requirements.md (feature folder under .semipilot/features/).
tools: ["search", "usages", "edit", "runCommands"]
---

Refine the idea below into a requirements document, following your role definition (`refiner.agent.md`) exactly —
it is the single source of truth for your process, output structure and constraints.

**The idea:** everything Dev typed after this command. If empty, ask for it and wait.

**Output:** `.semipilot/features/<slug>/requirements.md` with `status: draft` (propose the slug). Knowledge-layer
validation and tag confirmation first when the repo has one; impact analysis BEFORE drafting; observable acceptance
criteria, each tagged `[check: <ref>]`. End with your `### REFINER REPORT` / `### HANDOFF: spec-critic` block, then
stop — Dev runs `/spec-critic` next.
