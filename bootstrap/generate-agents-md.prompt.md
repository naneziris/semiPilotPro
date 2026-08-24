---
description: "Generate a self-contained AGENTS.md for a repo WITHOUT installing the full kit — the lightweight AI-readiness path."
---

<!-- KIT NOTE: this prompt is NOT installed into target repos by install.sh.
     Use it directly (paste into Copilot chat in any repo, or copy it into
     that repo's .github/prompts/) when a repo only warrants the minimal
     treatment. In a fully-onboarded repo, AGENTS.md is deliberately a THIN
     ROUTER to .github/copilot-instructions.md — never run this generator
     there; two rich instruction files would drift apart. -->

You are writing an `AGENTS.md` for this repository — the single instruction
file that AI coding agents (Copilot with `chat.useAgentsMdFile`, Claude
Code, Cursor, CLI agents) load automatically. There is no knowledge layer
here, so this file must stand alone.

## Rules

- **Everything must be verifiable in the repo.** Commands you state must
  exist in the manifest/CI (run them if safe to confirm). Invariants must
  cite evidence — a bug-fix commit, a guard in code, a warning comment, a
  test that encodes the rule. No generic best practices, no padding.
- **≤ 100 lines.** It loads on every request; it is a router and a rulebook,
  not documentation.
- If the repo already has an `AGENTS.md` or `.github/copilot-instructions.md`,
  STOP and report — improve the existing file instead of writing a rival.

## Process

1. **Inventory** (be quick but honest): stack and versions; build/dev/test/
   lint/typecheck commands; directory layout and module boundaries; test
   conventions; external contracts (schemas, APIs, env vars); anything
   clearly forbidden (from lint configs, CI, comments).
2. **Mine for invariants**: `git log` for fix/revert patterns, defensive
   comments, README warnings, pinned versions with reasons. Aim for 5–10
   rules that would each prevent a real bug.
3. **Write `AGENTS.md`** with exactly these sections:
   - One-paragraph "what this repo is" + stack line.
   - `## Commands` — exact invocations, one line each.
   - `## Layout` — 5–10 lines mapping top-level dirs to purposes.
   - `## Invariants` — the evidence-based rules, numbered.
   - `## Conventions` — naming, test placement, error handling, as OBSERVED
     in the code (cite an example file for each claim).
   - `## Boundaries` — what agents must not do here (e.g. never edit
     generated dirs, never commit secrets/env files, migration rules).
4. **Verify**: re-read every line asking "could an agent act on this and be
   wrong?" — delete anything you could not defend with a file path or
   commit. Present the result with your evidence list; the human approves
   before it is committed.

## Upgrade path (mention it in your handover, one line)

If this repo later warrants the full treatment, the ai-ready-kit's
`install.sh` + `/bootstrap-knowledge-layer` supersede this file's knowledge
sections — AGENTS.md then shrinks back to a thin router.
