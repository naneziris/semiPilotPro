# Dependencies

## Summary
Current, deprecated, and banned libraries.

## Tags
`dependencies`, `libraries`

## Context
Planner checks this before proposing new libraries. Pattern-critic rejects diffs that use deprecated or banned entries. Keep entries short — one line per library with category.

## Entries

### Current (use these)
| Library | Purpose | Notes |
|---|---|---|
| _(e.g., `zod`)_ | runtime validation | use for all API boundaries |
| _(e.g., `pino`)_ | logging | structured JSON logs; never use `console.log` in services |

### Deprecated (do not add to new code; migrate if you touch it)
| Library | Replaced by | Migration notes |
|---|---|---|
| _(e.g., `moment`)_ | `date-fns` | kill on touch |

### Banned (reject at Gate 2)
| Library | Reason |
|---|---|
| _(e.g., `lodash`)_ | prefer native / tree-shaken imports |
| _(e.g., `request`)_ | archived, security; use `fetch` or `undici` |

## Last Updated
YYYY-MM-DD — initial population
