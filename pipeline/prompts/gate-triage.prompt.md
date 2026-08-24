---
description: Pre-critic structural triage. Validates mechanical completeness of the artifact before invoking a critic. Returns PASS or STRUCTURAL_FAIL. Run in-context — do not invoke via the Agent tool.
---

# TASK: Gate Triage

Perform **mechanical** structural checks only. Do not reason about quality, coherence, or correctness — that is the critic's job. These checks are grep-level: section headers present, rows exist, strings found or absent.

Return PASS or STRUCTURAL_FAIL as the first word of your response.

---

## Gate 1 Triage (before @spec-critic)

Run these checks against the requirements file path you were given:

1. **Required sections present.** The file must contain all of these section headers (exact or close match):
   - `## Problem`
   - `## In Scope`
   - `## Out of Scope`
   - `## Impact Analysis`
   - `## Acceptance Criteria`
   - `## Assumptions`
   - `## Open Questions`
   - `## Knowledge References`

   If any are absent → **STRUCTURAL_FAIL**.

2. **Impact Analysis populated.** The `## Impact Analysis` section must contain:
   - A Consumers table with at least one data row (not just a header row).
   - A `Confidence:` line.

   If the table has only headers and no data rows, or `Confidence:` is missing → **STRUCTURAL_FAIL**.

3. **Acceptance Criteria populated.** `## Acceptance Criteria` must have at least one numbered or bulleted criterion. Empty section or single-word placeholder → **STRUCTURAL_FAIL**.

4. **No unfilled placeholders in critical sections.** Search `## Impact Analysis` and `## Acceptance Criteria` for: `<todo>`, `TBD`, `<placeholder>`, `TODO`. Any match → **STRUCTURAL_FAIL**.

---

## Gate 2 Triage (before @pattern-critic)

Run these checks against the current diff and the IMPLEMENTER REPORT:

1. **Test files in diff.** The diff must include at least one file matching `*.test.*`, `*_test.*`, or `*spec*`. If none → **STRUCTURAL_FAIL**.

2. **No lint suppression in diff.** Search the diff for any of:
   `eslint-disable`, `// nolint`, `@SuppressWarnings`, `# noqa`, `// tslint:disable`
   Any match → **STRUCTURAL_FAIL**.

3. **IMPLEMENTER REPORT present and complete.** The IMPLEMENTER REPORT must:
   - Exist in the context (not missing).
   - List all 11 YAML rail step lines (`read_plan` through `submit_for_pattern_critic`).
   If missing or fewer than 11 step lines → **STRUCTURAL_FAIL**.

4. **Conventions present.** Read the first line of `.github/copilot-instructions.md`. Empty or missing → **STRUCTURAL_FAIL**.

---

## Output Format

Return exactly this block and nothing else:

```
GATE <1|2> TRIAGE: <PASS | STRUCTURAL_FAIL>
<If STRUCTURAL_FAIL: one sentence naming the failed check and what is missing or present that it should not be.>
<If PASS: "All structural checks passed. Proceed to critic.">
```

No preamble. No reasoning. No suggestions. The critic does the reasoning — you only verify structure.
