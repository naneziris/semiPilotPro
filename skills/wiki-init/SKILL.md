---
name: wiki-init
description: Scaffold the seven-file Karpathy wiki in .wiki/ with seeded OVERVIEW and DATA_MODELS when detectable.
argument-hint: "[--dry-run] [--force]"
user-invocable: true
---

# Instructions

1. Runs `./run.py` in this directory.
2. Creates `.wiki/` with all seven template files: `OVERVIEW.md`, `ARCH_DECISIONS.md`, `DATA_MODELS.md`, `PATTERNS.md`, `DEPENDENCIES.md`, `API.md`, `CHANGELOG.md`.
3. Seeds `OVERVIEW.md` from detected `package.json`, `pyproject.toml`, or `README.md`.
4. Seeds `DATA_MODELS.md` from detected schema files (`schema.prisma`, `*.sql`, `models.py`) as a heads-up list for `@scribe` to fill out properly.
5. `--dry-run` prints the files and seed content that would be written without touching disk.
6. `--force` overwrites existing wiki files. Without `--force`, skips files that already exist.

Run this once at the start of using SemiPilot Pro on a new codebase. Re-run with `--force` only if you want to reset.
