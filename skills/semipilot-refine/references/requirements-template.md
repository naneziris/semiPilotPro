# requirements.md — required structure

Copy this structure exactly. Section names are parsed: the loop reads acceptance criteria from the section whose
heading contains "Acceptance", and knowledge tags from the `Tags:` line under *Knowledge References*.

Frontmatter: `type` is the conventional type of the change (`feat` | `fix` | `chore` | `refactor` | `docs`) and names
the branch; `status` stays `draft` — the spec critic sets `approved` after the human says so. Keep the frontmatter
free of comments.

```markdown
---
feature: <slug>
type: feat
status: draft
---
# Requirement: <short title>

## Problem
<2–4 sentences. What the user is trying to accomplish. Why the current state is insufficient.>

## In Scope
- <bullet>

## Out of Scope
- <explicit exclusions — "not doing X in this pass">

## Impact Analysis
**Confirmed tags:** <tags from _vocabulary.md confirmed by the user — or "no knowledge layer">

**Modules / cards touched:**
| Module or card | Why touched | Public contracts at risk | Breakage risk |
|---|---|---|---|
| `<card id or path>` | <reason> | <contract, or "none"> | low / medium / high |

**Invariants that constrain this change:** <quote the relevant card `invariants:` lines, or documented rules>

**Tests that exercise the touched surface:**
- `<test file>` — covers <which behaviour>

**Side-effect surfaces (state, providers, event handlers, lifecycle hooks):**
- <if any>

**Confidence:** <high | medium | low>. If `low`, list the specific unknowns in `Open Questions`.

## Acceptance Criteria
1. <observable outcome, "Given … When … Then …" or equivalent> [check: <ref>]

## Assumptions
- <any assumption the spec depends on — flag these clearly>

## Open Questions
- <question the planner must resolve> — default: <recommended answer>

## Knowledge References
- Tags: <the confirmed tags — the loop resolves these for every agent>
- Cards resolved: <card file paths, or "n/a">
- Knowledge updates expected: <cards / instructions / decisions.md / dependencies.md the scribe will update if this lands>
```

Rules of thumb:

- **Problem** says why, not how. If you find yourself naming a function, it belongs to the planner.
- **Out of Scope** is where most scope creep is stopped. Name the tempting neighbours explicitly.
- **Open Questions** always carry a default; the loop's planner turns unresolved ones into questions for the human
  before the run, and a default lets the human answer with one word.
- Keep the file under ~150 lines. A longer spec is usually two features.
