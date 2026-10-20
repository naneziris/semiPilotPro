# Write a standalone AGENTS.md (lightweight path, no cards)

`AGENTS.md` at the repository root is read natively by GitHub Copilot (VS Code chat, Copilot CLI, coding agent),
Claude Code (when there is no `CLAUDE.md`; otherwise import it from `CLAUDE.md` with a line `@AGENTS.md`), OpenAI
Codex, Cursor and most CLI agents. Use this when a repository warrants the minimal treatment.

## Rules

- **Everything must be verifiable in the repository.** Commands must exist in the manifests or CI (run them if safe).
  Invariants cite evidence — a bug-fix commit, a guard in code, a warning comment, a test that encodes the rule.
  No generic best practices, no padding.
- **≤ 100 lines.** It loads on every request; it is a router and a rulebook, not documentation.
- If an `AGENTS.md`, `CLAUDE.md` or `.github/copilot-instructions.md` already exists, STOP and offer to improve it
  instead of writing a rival. Two rich instruction files drift apart.

## Process

1. **Inventory:** stack and versions; build / dev / test / lint / typecheck commands; layout and module boundaries;
   test conventions; external contracts (schemas, APIs, env vars); anything clearly forbidden (lint configs, CI,
   comments).
2. **Mine invariants:** `git log` fix/revert patterns, defensive comments, README warnings, pinned versions with
   reasons. Aim for 5–10 rules that would each prevent a real bug.
3. **Write** `AGENTS.md` from `assets/templates/AGENTS.template.md`: what the repository is + stack; Commands;
   Layout (5–10 lines); Invariants (numbered, evidenced); Conventions (as observed — cite an example file for each);
   Boundaries (what agents must never do here).
4. **Verify:** re-read every line asking "could an agent act on this and be wrong?" — delete anything you cannot
   defend with a file path or commit. Present it with your evidence list; the user approves before committing.

Upgrade path (mention it in one line): the full knowledge layer (`semipilot kb init` + the bootstrap workflow) adds
cards and deterministic retrieval; `AGENTS.md` then gains the knowledge router block.
