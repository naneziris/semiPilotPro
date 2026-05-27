---
description: Cyclomatic complexity analysis with absolute thresholds. Outputs a machine-readable JSON verdict used by @pattern-critic and the implementer's YAML rail.
---

# TASK: Code Analyzer

You are running cyclomatic complexity analysis on one or more files.

## Usage

```
/code-analyzer path/to/file.ts
/code-analyzer path/to/file.py
/code-analyzer src/       # analyze all files in directory
```

If no path is provided, analyze all files changed in the current working tree (`git diff --name-only`).

## Steps

1. Run the script on the target path(s):

```bash
python skills/code-analyzer/run.py <path>
```

With `--dry-run` to preview without writing output files:

```bash
python skills/code-analyzer/run.py --dry-run <path>
```

2. Parse the JSON output. The schema is:

```json
{
  "verdict": "PASS | FAIL | WARN",
  "files": [
    {
      "path": "string",
      "functions": [
        {
          "name": "string",
          "complexity": 12,
          "exceeds_threshold": false,
          "exempt": false
        }
      ],
      "file_complexity_delta_percent": 5.2
    }
  ],
  "threshold": {
    "cyclomatic_complexity_max_per_function": 15,
    "file_complexity_increase_max_percent": 20
  }
}
```

3. Report findings:
   - Any function exceeding complexity 15 (FAIL unless `# complexity-exempt:` comment is present).
   - Any file with complexity increase > 20% (WARN — flag for Gate 2, do not block).
   - Overall verdict.

## Thresholds

| Threshold | Value | On breach |
|---|---|---|
| Per-function cyclomatic complexity | 15 | FAIL (blocks `/implement-plan` step 9 if not exempt) |
| File-level complexity increase | 20% | WARN (flagged at Gate 2, not blocking) |

A function can exceed 15 only with an explicit `# complexity-exempt: <reason>` comment. The reason must explain why the complexity cannot be reduced.
