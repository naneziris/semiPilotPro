---
name: project-map
description: Scan a monorepo or single repo and emit a markdown table of packages, locations, and internal dependencies.
argument-hint: "[--root DIR] [--dry-run]"
user-invocable: true
---

# Instructions

1. Runs `./run.py` in this directory.
2. Searches `packages/`, `apps/`, `libs/`, `services/` and the repo root for `package.json` / `pyproject.toml` / `go.mod` / `Cargo.toml`.
3. Outputs a markdown table: package name, type, location, internal dependencies.
4. Used by `@planner` to understand cross-package impact, and by `@spec-critic` to sanity-check feasibility claims.
5. `--dry-run` prints the directories that would be scanned without opening manifest files.

## Exit codes
- `0` — success
- `1` — nothing found (no manifests in expected locations)
