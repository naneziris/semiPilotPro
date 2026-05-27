---
description: Scaffold the seven-file Karpathy wiki in .wiki/ with seeded OVERVIEW and DATA_MODELS when detectable.
---

# TASK: Wiki Init

You are initializing the `.wiki/` directory for this project by running the wiki-init skill script.

## Steps

1. Confirm the `skills/wiki-init/run.py` script exists in the SemiPilot Pro installation. If not, stop and report the path it should be at.

2. Run the script:

```bash
python skills/wiki-init/run.py
```

Use `--dry-run` first to preview what will be created:

```bash
python skills/wiki-init/run.py --dry-run
```

3. Report which files were created and any seeded content detected from `package.json`, `pyproject.toml`, or schema files.

4. After `/wiki-init` completes on a **non-empty codebase**, immediately run `/patterns-seed` to seed `PATTERNS.md` with inferred conventions. Without this step, `@pattern-critic` will reject every diff on the first cycle.

## Exit

Report:
```
Wiki initialized.
Files created: <list>
OVERVIEW.md seeded: <yes/no>
DATA_MODELS.md seeded: <yes/no>

Next: run /patterns-seed (non-empty codebases) or /refine-requirements to start your first cycle.
```
