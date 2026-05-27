---
description: Concatenate wiki + codebase for long-context reads. Useful for deep analysis sessions.
---

# TASK: LLM Wiki

You are concatenating the wiki and relevant codebase files into a single long-context bundle for deep analysis.

## Steps

1. Run the script:

```bash
python skills/llm-wiki/run.py
```

Options:
```bash
python skills/llm-wiki/run.py --wiki-only         # just .wiki/ files
python skills/llm-wiki/run.py --include src/       # wiki + specific directory
python skills/llm-wiki/run.py --dry-run            # preview what would be bundled
```

2. The script outputs a single concatenated markdown file (or prints to stdout) that combines:
   - All seven `.wiki/` files in order.
   - Optionally, specified source directories.

3. Use the bundle as context for:
   - Large-scale refactor analysis.
   - Cross-cutting questions that span the full codebase.
   - Feeding to an external long-context model for second-opinion analysis.

## Notes

- The output can be large. Use `--wiki-only` for most pipeline work.
- FAISS indexing is optional and requires additional setup — see `skills/llm-wiki/README.md`.
