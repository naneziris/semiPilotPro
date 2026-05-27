---
name: patterns-seed
description: Infer naming, DI, error-handling, and test conventions from an existing codebase and seed PATTERNS.md so the Pattern Critic has something to enforce on the first cycle.
argument-hint: "[--dry-run] [--force] [--root path] [--sample-size N]"
user-invocable: true
---

# Instructions

1. Runs `./run.py` in this directory.
2. Scans the codebase from `--root` (default: current working directory) and samples up to `--sample-size` (default: 30) source files per detected language.
3. Extracts:
   - **Naming conventions**: file naming (kebab/snake/camel/Pascal), function naming, class naming, constant naming. Reports the dominant style and the per-style frequency.
   - **Import / module organization**: relative vs. absolute imports, barrel files, index re-exports.
   - **Dependency injection style**: constructor injection, parameter passing, module-level singletons, dependency factories, framework DI (NestJS, Spring, etc.).
   - **Error handling**: throw / Result types / callback errors / Option types. Reports the dominant style.
   - **Test conventions**: test file naming pattern, test framework (Jest/Vitest/pytest/etc.), arrange-act-assert vs. given-when-then, mocking style.
4. Writes a structured `.wiki/PATTERNS.md` using the standard wiki template, seeded with the detected conventions and marked as `Status: seeded — refine as features land`.
5. `--dry-run` prints the inferred patterns and the would-be file content without touching disk.
6. `--force` overwrites an existing non-empty `PATTERNS.md`. Without `--force`, refuses to overwrite and exits 1.

## When to run

- Once, immediately after `#wiki-init`, on an existing codebase.
- Re-run with `--force` after a major refactor that changes the project's dominant conventions.

## What it does NOT do

- Does not invent patterns. Reports only what is observable from the existing code.
- Does not enforce anything. The Pattern Critic does enforcement; this skill only writes the file the critic reads.
- Does not edit any other wiki file. Touches `PATTERNS.md` and nothing else.

## Supported file extensions

`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.java`, `.cs`, `.rb`

## Exit codes

- `0` — patterns inferred and written (or printed in `--dry-run`)
- `1` — `PATTERNS.md` already populated and `--force` not set, or no source files found
- `2` — no `.wiki/` directory present (run `#wiki-init` first)
