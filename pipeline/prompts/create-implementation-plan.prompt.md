---
agent: planner
description: Turn an APPROVED requirements.md into a concrete implementation plan with files, tests, steps, and knowledge updates.
model: Claude Sonnet 4.6 (copilot)
tools: ["search", "usages", "edit", "runCommands"]
---

# TASK

Write the implementation plan for the APPROVED requirements, following your
role definition (`planner.agent.md`) exactly — it is the single source of
truth for your pre-flight checks, output structure, and constraints.

**Input:** `.github/requirements/requirements.md` (or
`requirements-index.md` + sub-files), APPROVED by `@spec-critic`. Run your
pre-flight check first; stop and report if it is missing or unapproved.

**Output location:** `.github/implementation-plan.md` — or, for an index
input, one plan per sub-requirement under `.github/plans/NN-<slug>-plan.md`
plus a top-level `implementation-plan-index.md` in dependency order.

Follow your full process: re-resolve from the requirements' tags (never
re-infer), take file paths from the cards, honor invariants, map every
acceptance criterion to a test, plan the knowledge updates. End with your
`### PLANNER REPORT` / `### HANDOFF: implement-plan` block, then stop.
