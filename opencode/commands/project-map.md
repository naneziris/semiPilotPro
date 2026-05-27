---
description: Scan a monorepo or single repo and emit a markdown table of packages, locations, and internal dependencies.
---

# TASK: Project Map

You are generating a map of this project's packages and their internal dependencies.

## Steps

1. Run the script:

```bash
python skills/project-map/run.py
```

With `--dry-run` to preview:

```bash
python skills/project-map/run.py --dry-run
```

2. The output is a markdown table in this format:

```markdown
| Package | Location | Depends on |
|---|---|---|
| core | packages/core | — |
| api | packages/api | core |
| web | apps/web | core, api |
```

3. Report the table and note:
   - Any circular dependencies detected.
   - Any packages with no consumers (potential dead code).
   - Any packages imported from >3 other packages (high-impact change surfaces).

## When to use

- Before starting a refactor to understand blast radius.
- When the refiner's impact analysis needs a structural overview.
- When `@spec-critic` or `@planner` needs to understand architectural boundaries.
