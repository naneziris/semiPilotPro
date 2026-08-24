# Dependencies — allowlist & policy

Owned by `@scribe` (pipeline) — humans may edit via PR. The planner must cite
this file for any dependency change; `@pattern-critic` rejects diffs that
import a library not listed as current.

## Policy

- **Default is NO.** New runtime dependencies need explicit justification in an
  implementation plan (and usually an ADR).
- {{TODO: repo-specific policy lines — package manager, lockfile rules, bundle budgets.}}

## Current — runtime

| Library | Why |
|---|---|
| {{TODO: from the manifest (package.json / pyproject / go.mod), with one-line purpose each}} | |

## Current — dev

{{TODO: dev/test tooling, one line.}}

## Banned / avoid

- {{TODO: libraries the team has decided against, with the reason — this list is what gives the pattern-critic teeth.}}

## Deprecated

{{TODO: currently-used libraries being migrated away from, or "None currently."}}

## Last Updated
{{TODO: YYYY-MM-DD}} — seeded at bootstrap
