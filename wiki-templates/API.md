# Public API

## Summary
Public API signatures and contracts.

## Tags
`api`, `contracts`

## Context
Breaking changes to anything listed here require an authorized plan entry. Pattern-critic cross-checks diffs against this file. "Public" means anything consumed outside its module: HTTP endpoints, library exports, CLI commands, event contracts.

## Entries

### HTTP endpoints

#### `POST /example` _(example — replace)_
- **Added / Changed / Removed:** Added
- **Signature:**
  - Request: `{ field: string }`
  - Response (200): `{ id: string, field: string }`
  - Response (400): `{ error: string, code: "VALIDATION_ERROR" }`
- **Stability:** stable
- **Notes:** —

### Library exports

#### `fn(arg: Type) -> Ret` _(example — replace)_
- **Module:** `src/lib/example`
- **Stability:** stable | experimental | deprecated
- **Notes:** —

### CLI commands

#### `cli-name subcommand [--flag]`
- **Stability:** stable
- **Notes:** —

## Last Updated
YYYY-MM-DD — initial population
