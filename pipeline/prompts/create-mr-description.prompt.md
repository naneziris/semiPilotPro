---
description: Generate a structured merge request description from requirements.md, implementation-plan.md, and the git diff.
model: Claude Sonnet 4.6 (copilot)
tools: ["search", "usages", "runCommands"]
---

# TASK

You are generating a merge request description for the change produced in the most recent pipeline cycle. You read three sources and produce one structured document. You do not invent content — every claim must trace back to an input source.

Take a deep breath and work through this step by step.

---

# INPUTS

Read these in order:

1. `.github/requirements/requirements.md` — the WHY (problem, scope, acceptance criteria).
2. `.github/implementation-plan.md` — the HOW (files changed, steps, risks, knowledge updates).
3. The git diff — run `git diff main` (or `git diff origin/main`, or `git diff HEAD~1` as fallback). Read it in full.

Also check:
- `.github/rejection-log.md` — if it exists and has entries for this cycle, note the iteration count in the Notes for Reviewer section.
- The implementer's `explain_test_changes` output from the IMPLEMENTER REPORT (if any existing tests were modified, include the reasons in Notes for Reviewer).

**Pre-flight:** if either `requirements.md` or `implementation-plan.md` does not exist, stop immediately and say: "Missing [filename]. Run the full pipeline before generating an MR description."

---

# OUTPUT FORMAT

Produce exactly this markdown block. Do not add extra sections or omit any heading.

```markdown
## What

<2–4 sentences describing the observable behavior change from the user's perspective. Do not write "I implemented" — describe what is different after this change lands. Source: requirements.md § Problem and § In Scope.>

## Why

<2–4 sentences explaining the motivation. What was broken, missing, or needed improvement, and why this change addresses it now. Source: requirements.md § Problem.>

## Changes

<Derived from implementation-plan.md § Files to Change.>

| File | Change | Reason |
|---|---|---|
| path/to/file | created / modified / deleted | short reason |

## Tests

<Derived from implementation-plan.md § Test Plan.>

| Criterion | Test File | Type |
|---|---|---|
| AC description | path/to/test | unit / integration / e2e |

## Acceptance Criteria

<Copy from requirements.md § Acceptance Criteria as a checkbox list. Reviewers use this to verify the change manually.>

- [ ] <AC1>
- [ ] <AC2>

## Risks & Rollback

<Derived from implementation-plan.md § Rollout & Risk. Use 2–4 bullets. If the plan says "none", write "None identified.">

- <risk or rollback note>

## Notes for Reviewer

<Anything a reviewer should pay particular attention to. Include:
- Non-obvious design choices visible in the diff.
- Reasons for any modified existing tests (from explain_test_changes output, if present).
- Complexity flags from the Pattern Critic verdict (if any were flagged but not rejected).
- Iteration count if the cycle had critic rejections (e.g., "This passed Gate 2 on attempt 2 — see .github/rejection-log.md for the first rejection.").
If none of the above apply, write "None.">
```

---

# RULES

- Do not invent content. If a section has nothing to draw from, write "None identified." — do not omit the heading.
- Do not include implementation detail that belongs in code comments.
- Do not reference internal pipeline terms (YAML rail, Gate 1, etc.) — the MR description is for code reviewers, not pipeline users.
- Keep each prose section under 5 sentences. Tables speak for themselves.

---

# EXIT

After producing the MR description, say:

```
MR description generated. Copy the block above into your MR.

Next: run @scribe to update the knowledge layer.
```

Then stop.
