---
description: Write unit tests for an existing file, following wiki patterns. No pipeline required — outputs a report ready for @pattern-critic.
---

# TASK

You are writing unit tests for an existing source file. The code already exists — you are not building a new feature. Your job is to cover observable behavior, not implementation details. You must follow the test conventions in `.wiki/PATTERNS.md` exactly.

Take a deep breath and work through this step by step.

# PRE-FLIGHT

1. Confirm `.wiki/PATTERNS.md` exists and is non-empty. If it is empty or missing, stop and report: "Wiki patterns not populated. Fill in `.wiki/PATTERNS.md` with your test conventions before running `/write-tests`."
2. Identify the target file:
   - If the user passed a path as an argument, use that.
   - Otherwise, use the file currently open in the editor.
   - If neither is clear, stop and ask: "Which file should I write tests for?"
3. Check whether a test file for the target already exists (search for `*.test.*`, `*_test.*`, `*spec*` co-located or in the project's test folder). If one exists, read it before writing anything — do not duplicate tests that already cover the behavior.

# STEPS

## Step 1: read_patterns

Read `.wiki/PATTERNS.md` completely. Extract and note:
- Test framework and runner (Jest, Vitest, pytest, etc.)
- Test file naming convention and location (co-located vs. `/tests/` folder)
- Test structure style (describe/it, AAA, fixture-based, etc.)
- How mocks and stubs are used
- Any banned patterns (e.g. no `any` in assertions, no `.only` left in committed tests)

## Step 2: read_target_file

Read the target source file completely. Identify:
- Every exported function, class, and method
- All meaningful input/output combinations (happy paths)
- Edge cases: empty inputs, null/undefined, boundary values, type coercions
- Error conditions: what throws, what returns an error shape
- Any side effects (writes, emits, calls external dependencies)

Do not test private functions or internal implementation choices. Test what callers depend on.

## Step 3: map_behaviors_to_tests

Before writing any code, produce a test plan in this format:

```
### Test Plan: <target file name>

| Behavior | Test type | Input | Expected output |
|---|---|---|---|
| <description> | unit | <input summary> | <expected> |
```

List every row you intend to cover. If a behavior is untestable without mocking a dependency, note the mock strategy in the `Test type` column (e.g. `unit / mock DB`).

## Step 4: write_test_file

Write the test file following the conventions from Step 1.

Rules:
- One `describe` block per exported unit (function/class/method).
- Name each test with the behavior it asserts, not the implementation (`"returns null when input is empty"` not `"tests the null branch"`).
- Follow AAA: Arrange, Act, Assert — one assert per test where possible.
- Mock only external dependencies (network, DB, file system, time). Do not mock the module under test.
- Do not use `.skip` or `.only`.
- Do not leave TODO comments.
- Do not suppress lint rules.

Place the file at the path dictated by `PATTERNS.md` conventions.

## Step 5: run_tests

Run the test suite for the new test file only.

- All tests must pass. The code already exists — if a test fails, the test is wrong (or reveals a real bug — report it).
- If a test fails because it found a genuine bug: note it in the report, mark that test with `// BUG: <description>` temporarily, and move on. Do not fix the source code.
- Do not run the full suite — that is @pattern-critic's gate.

## Step 6: report

Emit this block and stop. Do not invoke @pattern-critic yourself.

```
### WRITE-TESTS REPORT

Target file: <path>
Test file written: <path>

Test plan executed:
| Behavior | Result |
|---|---|
| <behavior> | pass / bug-found |

Bugs found (if any):
- <description of the bug, or "none">

Coverage areas:
- Happy paths: <list>
- Edge cases: <list>
- Error conditions: <list>
- Untested (and why): <list, or "none">

Ready for @pattern-critic.
```

# HARD CONSTRAINTS

- **Do not modify the source file.** If writing tests reveals a bug, report it — do not fix it here.
- **Do not write to `.wiki/`.** If new patterns emerge from this work, note them in the report; `@scribe` will record them after `@pattern-critic` approves.
- **Do not test private internals.** Only test what is exported and what callers depend on.
- **Do not fabricate passing tests.** If you cannot make a test pass without modifying source, mark it as `bug-found` in the report.
- **Follow `PATTERNS.md` exactly.** If your instinct conflicts with a pattern in the wiki, the wiki wins.
