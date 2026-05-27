---
description: Infer naming, DI, error-handling, and test conventions from an existing codebase and seed PATTERNS.md. Required for adopting SemiPilot Pro on a non-empty repo.
---

# TASK: Patterns Seed

You are seeding `.wiki/PATTERNS.md` by running the patterns-seed skill script against the existing codebase.

## When to use

Run this immediately after `/wiki-init` on any non-empty codebase. Without seeded patterns, `@pattern-critic` has nothing to enforce on the first cycle and will reject every diff.

## Steps

1. Confirm `.wiki/PATTERNS.md` exists (created by `/wiki-init`). If not, run `/wiki-init` first.

2. Preview the inferred patterns:

```bash
python skills/patterns-seed/run.py --dry-run
```

3. Review the preview. If it looks reasonable, run for real:

```bash
python skills/patterns-seed/run.py
```

4. Read the resulting `.wiki/PATTERNS.md` and confirm:
   - Naming conventions were detected (files, functions, classes).
   - DI patterns were detected (if applicable).
   - Error-handling style was detected.
   - Test conventions were detected (framework, file location, structure).

5. If any section looks wrong or incomplete, note it for Dev — do not silently accept bad patterns. Seeded patterns are best-effort; `@scribe` refines them as features land.

## Exit

Report:
```
PATTERNS.md seeded.
Detected:
- Naming: <summary>
- DI: <summary or "not detected">
- Error handling: <summary>
- Tests: <framework, location, structure>

Review .wiki/PATTERNS.md and correct any misdetections before your first /implement-plan run.
```
