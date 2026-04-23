---
name: llm-wiki
description: Concatenate the .wiki/ (plus optional codebase files) into a single long-context document, or semantically query it. Concat is the default; FAISS is opt-in.
argument-hint: "concat [--source DIR] [--out FILE] | query --q 'question' [--k 5] | ingest --source DIR"
user-invocable: true
---

# Instructions

Three subcommands:

1. `concat` (default, recommended) — Concatenates `.wiki/` files (optionally plus source files) into one `wiki-context.md` under a word cap. This is what agents load at the start of a task for full context.
2. `query` — Semantic search against a FAISS index built via `ingest`. Use only for very large codebases where concat exceeds the context cap.
3. `ingest` — Build a FAISS vector index. Opt-in — most projects don't need this.

## When to use which

- **Under 40k words of wiki + key source**: `concat` is enough. Simple, deterministic, no dependencies.
- **Over 40k words**: `concat` will truncate. Either narrow the `--source` or use `ingest` + `query`.

## Flags common to all modes

- `--dry-run`: print the plan without writing.
- `--exclude`: additional glob patterns to skip (default: `node_modules`, `.git`, `dist`, `build`, `.venv`, `*.lock`).

## Dependencies

- `concat`: standard library only.
- `ingest` / `query`: requires `sentence-transformers`, `faiss-cpu`, `numpy`. Install only if you need FAISS mode.

## Exit codes
- `0` — success
- `1` — user error (bad args, missing source)
- `2` — missing FAISS deps when needed
