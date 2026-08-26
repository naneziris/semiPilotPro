---
agent: refiner
description: Turn a raw user idea into a precise, testable requirements.md that can pass Gate 1 (spec-critic).
model: Claude Sonnet 4.6 (copilot)
tools: ["search", "usages", "edit", "runCommands"]
---

# TASK

Refine the user idea below into a requirements document, following your role
definition (`refiner.agent.md`) exactly — it is the single source of truth
for your process, output structure, and constraints.

**The idea:** everything the user typed after this command. If empty, ask
for it and wait.

**Output location:** `.github/requirements/` — a single `requirements.md`,
or `requirements-index.md` + `NN-<slug>.md` sub-files if the decomposition
policy (`semipilot-core.md > Decomposition Policy`) triggers.

Follow your full process: knowledge-layer validation first, tag proposal
with Dev confirmation, kb-resolve-only retrieval, impact analysis BEFORE
drafting, observable acceptance criteria. End with your
`### REFINER REPORT` / `### HANDOFF: spec-critic` block, then stop — Dev
(or `/run-pipeline`) invokes `@spec-critic` next.
