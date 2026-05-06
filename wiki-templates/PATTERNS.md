# Code Patterns

## Summary
Naming conventions, DI patterns, error handling, and test standards.

## Tags
`conventions`, `testing`, `patterns`

## Context
Pattern-critic (Gate 2) reads this file to approve or reject diffs. Every accepted convention in this codebase is documented here. If a pattern is not in this file, it is not enforceable and the critic will not reject on it.

## Entries

### Naming
- **Files:** _(e.g., kebab-case.ts; components PascalCase.tsx)_
- **Classes/Types:** PascalCase
- **Functions/variables:** camelCase (JS/TS) / snake_case (Python)
- **Constants:** SCREAMING_SNAKE_CASE
- **Test files:** `*.test.ts` next to source, not in a separate `__tests__` dir

### Dependency Injection
- _(e.g., constructor injection; no service locators)_
- _(e.g., use `container.register()` for singletons)_

### Error handling
- _(e.g., throw typed errors extending `AppError`)_
- _(e.g., never swallow errors silently; always log with context)_
- _(e.g., HTTP handlers return structured `{ error, code }` not raw strings)_

### Testing
- **Framework:** _(e.g., vitest / pytest)_
- **Style:** arrange / act / assert blocks with blank lines between
- **Coverage:** every acceptance criterion has a test; unit tests for pure logic, integration tests for persistence
- **No mocks of the database** — use a real test DB
- **Do not use `.skip` or `.only` in merged code**
- **Tests must exist as files on disk.** Implementation is not complete unless test files (`*.test.*`, `*_test.*`) are present in the diff. The pattern critic verifies file existence — the implementer's self-report is not accepted.

### Imports
- _(e.g., absolute imports via workspace aliases; no `../../..`)_

### Anti-patterns (reject on sight)
- _(e.g., `any` type in TypeScript)_
- _(e.g., function longer than 50 lines without refactor)_
- **No lint suppression.** Never add `eslint-disable`, `// nolint`, `@SuppressWarnings`, `# noqa`, or any equivalent suppression comment. If a lint rule fires, fix the code. An exception requires explicit approval from Dev, logged in `ARCH_DECISIONS.md`.

## Last Updated
YYYY-MM-DD — initial population
