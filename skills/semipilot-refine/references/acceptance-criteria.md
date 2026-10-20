# Writing acceptance criteria with `[check: <ref>]` tags

Every acceptance criterion ends with a tag that names the machine check proving it. The unattended loop builds
from these tags: the planner maps every task to refs, the test-writer names one locked test after each ref, and the
run is "done" only when those checks pass. An untagged criterion fails the loop's preflight.

## The tag

`[check: <ref>]`, where `<ref>` is one of:

| Kind | Example | Meaning |
|---|---|---|
| Test name or unique substring | `[check: test_csv_has_header]` | A test whose name contains this ref will exist and must pass |
| Global check | `[check: lint]`, `[check: typecheck]`, `[check: build]` | That configured check must pass |

Use the repository's test naming style: `test_snake_case` for Python, `exports csv header` / `exportsCsvHeader`
for Jest/Vitest names, `TestCsvHeader` for Go.

## Good and bad

| Bad | Why | Good |
|---|---|---|
| "Export works correctly" | not observable | "Exporting 3 orders produces a CSV with a header row and 3 data rows [check: test_export_three_orders]" |
| "Handle errors gracefully" | which errors? what happens? | "Exporting with no orders returns a CSV with only the header row [check: test_export_empty]" |
| "Fast enough" | no threshold, no check | "Exporting 10 000 orders completes in under 2 s on CI [check: test_export_10k_under_2s]" — or move to Out of Scope |
| "Code follows conventions" | not a behaviour | `[check: lint]` on its own line, if it matters |
| Two behaviours in one criterion | one ref cannot prove both | split into two criteria with two refs |

## Checklist before handing to the spec-critic

- [ ] Every criterion is an observable outcome a test can assert.
- [ ] Every criterion ends with exactly one `[check: <ref>]`.
- [ ] Refs are unique and follow the repository's test naming style.
- [ ] The criteria cover every bullet of *In Scope*, and nothing outside it.
- [ ] Edge cases the idea implies (empty input, permissions, failures of external dependencies) are either criteria
      or listed under *Out of Scope*.
