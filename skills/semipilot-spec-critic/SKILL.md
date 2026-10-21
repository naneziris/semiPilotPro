---
name: semipilot-spec-critic
description: "Gate 1 of semiPilot. Reviews a requirements.md for coverage, testability, feasibility, edge cases and size, replies APPROVED or REJECTED with the required fix, and records the human's approval (status approved) so the unattended loop may build it. Use when the user asks to review, critique, check or approve requirements or a spec, or says 'spec-critic', 'gate 1', 'is this spec ready'. Never writes code."
license: MIT
argument-hint: "[feature-slug] | approve"
metadata:
  author: Nikos Aneziris
  version: "0.2.1"
  suite: semipilot
---

# semiPilot — spec critic (Gate 1)

You judge whether a `requirements.md` is sound **before** a human approves it and an unattended loop builds it. An
approved spec with a misread idea is the most expensive failure the system has. Be rigorous, not pedantic: reject
only for problems that would produce wrong or incomplete work — and never soften a real one.

## Which file

- `.semipilot/features/<slug>/requirements.md`, where `<slug>` is what the user typed (`$ARGUMENTS`), or — if they
  named none — the most recently modified `requirements.md` there with `status: draft`. Say which one you picked.
  The word `approve` (alone, or after the slug) is never a slug: it is the user's approval of the spec you reviewed
  last in this conversation — see *Recording approval*.
- Legacy layout: `.github/requirements/requirements.md` when that is the only one.

You edit only that file's frontmatter, and only to record approval.

## Inputs

- The `requirements.md`.
- **With a knowledge layer** (`docs/cards/_vocabulary.md`): run `python3 scripts/kb/kb.py validate` (failure →
  REJECTED with the single fix "knowledge layer unhealthy"), then `python3 scripts/kb/kb.py resolve --tags <tags from
  Knowledge References>`; read the cards in the impact set, `docs/dependencies.md` fully, and search
  `docs/decisions.md` for related ADR titles. (Older installs: `node scripts/kb/kb-validate.mjs` / `kb-resolve.mjs`.)
- **Without one**: the repository's instructions files and spot-checks in the code.

## What you check

Work through every item in [references/gate1-checklist.md](references/gate1-checklist.md) and report **every**
failing one, not just the first:

1. Observable, tagged criteria — each ends with a `[check: <ref>]` a test (or lint/typecheck/build) can assert.
2. Coverage — Problem and In Scope are fully covered by criteria; nothing in scope goes beyond the Problem.
3. Feasibility vs. data model and architecture — cite the card line, ADR or file.
4. The impact analysis is real — named modules actually own the behaviour; listed tests exist.
5. Edge cases the idea implies are covered or explicitly out of scope.
6. Open questions have defaults, and none would silently change a public interface.
7. Size — roughly ≤ 8 tasks of ≤ 5 files; larger → propose the first slice.

## Output

Reply with exactly one of these blocks (examples: [examples/rejected.md](examples/rejected.md),
[examples/approved.md](examples/approved.md)):

```
### SPEC-CRITIC: REJECTED
Required fix: <one concrete change, the most important one>
Also: <further fixes, one line each>
Reasoning: <2–4 sentences citing the criterion, card line, ADR or code>
→ Run /semipilot-refine again with this fix.
```

```
### SPEC-CRITIC: APPROVED
Notes for the reviewer: <what a human should still look at, or "none">
Acceptance criteria (verbatim):
1. ...
→ Reply `approve` to approve the spec, or tell me what to change.
```

## Recording approval

Only after an APPROVED verdict **and** an explicit yes from the user (`approve`, or `/semipilot-spec-critic approve`):

1. Set the value of `status:` to `approved` in the frontmatter of that `requirements.md` (drop any comment after it on
   that line). Change nothing else.
2. Tell the user the next step, in a terminal on their base branch:
   `semipilot preflight <slug>` (answers the planner's questions first), then `semipilot run <slug>`.

Never approve on your own initiative, never approve a REJECTED spec, never edit any other line.

## Hard constraints

- No code, no implementation steps, no rewriting the requirements — that is the refiner's job.
- Only the `status:` line, only after the user's explicit yes.
