# Data Models

## Summary
Schemas, key types, and their relationships.

## Tags
`schema`, `database`, `types`

## Context
Spec-critic reads this to check feasibility. Keep schema changes current here or Gate 1 will reject specs as unverifiable. Include enough detail to answer "can the schema support this spec?"

## Entries

### Core entities
| Entity | Storage | Key fields | Relationships |
|---|---|---|---|
| `User` | postgres `users` | id, email, created_at | has many `Session` |
| _(add entries)_ | | | |

### Schema files
- `path/to/schema.prisma` — source of truth for ORM models
- `path/to/migrations/` — ordered migrations

### Invariants
- _(e.g., email is unique and case-insensitive)_
- _(e.g., soft-deletes via `deleted_at`, never hard delete)_

## Last Updated
YYYY-MM-DD — initial population
