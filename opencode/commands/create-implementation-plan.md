---
description: Turn an APPROVED requirements.md into a concrete implementation plan with files, tests, steps, and wiki updates.
---

# TASK

You are writing `.github/implementation-plan.md` from an APPROVED `requirements.md`. You must not write final code. The implementer will follow your plan step-by-step — if it is vague, the implementation will be vague.

Take a deep breath and work through this step by step.

# PRE-FLIGHT CHECK

1. Confirm `.github/requirements/requirements.md` (or `requirements-index.md` + sub-files) exists and was APPROVED by `@spec-critic`. If not, stop and report.
2. Read all seven `.wiki/` files. Not just the ones cited in the spec — all of them.
3. **Read the Impact Analysis section** of the requirements in full. Every consumer listed is a candidate `Files to Change` entry. Every side-effect surface is a candidate test case.
4. Scan the codebase for every file you expect to touch. Confirm they exist.

If any file the spec references does not exist in the codebase, raise it as a `Blocking Question` rather than guessing.

If your plan does not address every `Breakage risk: high` consumer the impact analysis identified, either add it to the plan or document under `Implementation Steps` why no change is needed. Leaving a high-risk consumer silently unaddressed is the failure mode this section prevents.

# STEPS

## 1. Write the plan to `.github/implementation-plan.md`

Use this exact structure:

```markdown
# Implementation Plan: <title matching requirements>

## Summary
<2–3 sentences. What we're building and why.>

## Files to Change
| Path | Change Type | Reason |
|---|---|---|
| path/to/file.ts | create / modify / delete | short reason |

## Test Plan
| Criterion (from requirements.md) | Test Type | Test File | What it asserts |
|---|---|---|---|
| AC1 | unit / integration / e2e | path/to/foo.test.ts | <assertion> |

## Implementation Steps
1. <atomic step>
2. <atomic step>

## Dependencies
- New libraries: <none | list with justification referencing .wiki/DEPENDENCIES.md>
- Removed libraries: <none | list>

## Wiki Updates Required
- `ARCH_DECISIONS.md`: <new ADR title, or "no change">
- `DATA_MODELS.md`: <schema delta, or "no change">
- `PATTERNS.md`: <new pattern, or "no change">
- `DEPENDENCIES.md`: <dep change, or "no change">
- `API.md`: <signature delta, or "no change">
- `CHANGELOG.md`: <user-facing line>

## Rollout & Risk
- Reversibility: <trivial | requires migration | irreversible>
- Feature flag: <yes/no, name>
- Known risks: <list, or "none">
```

## 2. Every acceptance criterion needs a test

Cross-check: every row in `requirements.md > Acceptance Criteria` must appear in the `Test Plan`. If one does not map to a test, either add the test or explain why it is inherently untestable (rare — usually means the criterion is wrong).

## 3. Steps must be atomic

"Implement the feature" is not a step. "Add method `UserRepository.findByEmail(email: string): Promise<User | null>`" is.

An atomic step:
- Touches one logical concern.
- Can be verified independently (tests compile, a function returns expected shape, etc.).
- Can be reverted without breaking unrelated steps.

## 4. No new dependencies without `DEPENDENCIES.md` justification

If the plan adds a library, it must cite the relevant entry in `.wiki/DEPENDENCIES.md`. If the library is not listed, add a `## Blocking Questions` section and ask Dev to categorize it first.

## 5. No final code

You may include function signatures and type definitions to clarify intent. Full function bodies are not allowed — those belong in `/implement-plan`.

## 6. Index inputs

If the input is `requirements-index.md`, produce one `implementation-plan.md` per sub-requirement under `.github/plans/NN-<slug>-plan.md`, AND a top-level `implementation-plan-index.md` listing them in dependency order. Each sub-plan is independently runnable.

## 7. Exit

End with:

```
### PLANNER REPORT
Output:
- <path(s) to plan file(s)>
Impact-analysis coverage: every high-risk consumer addressed: <yes | no with list>

### HANDOFF: implement-plan
target: <path to the plan file the implementer should run>
```

Then stop.
