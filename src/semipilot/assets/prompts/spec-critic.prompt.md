---
agent: spec-critic
description: semiPilot Gate 1 — review requirements.md, then record Dev's approval so PilotInLoop can run it.
tools: ["search", "usages", "edit", "runCommands"]
---

Review the feature's `requirements.md` following your role definition (`spec-critic.agent.md`) exactly: run every
check, reply APPROVED or REJECTED in the given format, and only set `status: approved` when Dev explicitly approves.

**Feature:** the slug Dev typed after this command, if any; otherwise the most recently modified
`.semipilot/features/*/requirements.md` with `status: draft` (say which one you picked).

If Dev typed `approve` (or an equivalent clear yes) after an earlier APPROVED verdict in this conversation, record
the approval and tell them to run `semipilot run <slug>`.
