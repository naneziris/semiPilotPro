---
name: code-analyzer
description: Cyclomatic complexity analysis with absolute thresholds. Outputs a machine-readable JSON verdict used by pattern-critic and the implementer's YAML rail.
argument-hint: "path/to/file [--dry-run] [--threshold N] [--baseline path]"
user-invocable: true
---

# Instructions

1. Runs `./run.py` in this directory against a single file.
2. Computes a rough cyclomatic complexity score per function by counting branching keywords (`if`, `elif`, `for`, `while`, `case`, `catch`, `and`, `or`, `&&`, `||`, ternary).
3. Flags any function exceeding `--threshold` (default 15) unless the line contains `# complexity-exempt:` or `// complexity-exempt:`.
4. If `--baseline <path>` is provided, compares total file complexity to the baseline and reports percent delta.
5. Output is JSON — Gate 2 (`@pattern-critic`) parses this directly.
6. `--dry-run` prints what would be analyzed without reading the file.

## Supported file extensions
`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.java`, `.cs`

## Exit codes
- `0` — all functions below threshold
- `1` — at least one function exceeds threshold (used by YAML rail to block)
- `2` — file not found or unparseable
