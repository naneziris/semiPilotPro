---
name: semipilot-knowledge
description: "Builds and maintains a deterministic codebase knowledge layer — one card per module, a closed tag vocabulary, and stdlib-Python tooling (kb.py) that validates the cards, resolves tags to an exact reading list, and detects drift and stale cards. Use when the user wants to make a repository AI-ready, bootstrap or set up the knowledge layer, write or update module cards, run an impact analysis for a change, sync cards after a change, catch up after pulling teammates' work, or write an AGENTS.md. Also use when asked 'which files matter for <change>'."
license: MIT
compatibility: "Needs python3 (3.9+). The included scripts/kb.py uses only the standard library and git."
argument-hint: "bootstrap | impact <change> | new-card <module> | sync | catchup | agents-md"
metadata:
  author: Nikos Aneziris
  version: "0.2.1"
  suite: semipilot
---

# semiPilot — knowledge layer

A knowledge layer replaces "grep around until something looks relevant" with a lookup: context is **resolved, not
searched**. Same tags in, same files out, every time — so impact analysis is auditable and agents read a small,
correct set instead of the whole codebase.

| Piece | Where | Role |
|---|---|---|
| Closed vocabulary | `docs/cards/_vocabulary.md` | The only entry point: 20–50 tags, human-owned, new tags by review only |
| Module cards | `docs/cards/<module>.md` | Strict frontmatter (`owns`, `depends_on`, `public_contracts`, `code`, `docs`, `invariants`) + 3–8 sentence summary, ≤ 80 lines |
| Manifest | `docs/cards/manifest.json` | Generated index, committed, never hand-edited |
| Deep docs | `docs/deep/*.md` | Read only when a card points there |
| Tooling | `scripts/kb/kb.py` | `validate`, `index [--check]`, `resolve --tags`, `drift`, `guard`, `catchup [--mark]` |
| Instructions | `AGENTS.md` (+ `CLAUDE.md` / `.github/copilot-instructions.md`) | Always-loaded router: commands, invariants, how to retrieve |
| Enforcement | `.githooks/pre-commit`, `.github/workflows/knowledge-layer.yml` | Block broken cards and stale manifests; nag on stale cards |

How retrieval works, rung by rung: [references/retrieval.md](references/retrieval.md).

## The tool

`kb` below means `python3 scripts/kb/kb.py` (Windows: `py scripts/kb/kb.py`). In a repository without it, use the
copy shipped in this skill: `python3 <this skill>/scripts/kb.py --root <repo> <command>` — or install the layer with
`semipilot kb init` when the semipilot CLI is available. All commands are read-only except `index` (writes the
manifest) and `catchup --mark` (writes a marker inside `.git/`).

## Workflows — pick the one the user asked for

| User intent | Workflow | Cost |
|---|---|---|
| "make this repo AI-ready", "set up / bootstrap the knowledge layer" | [references/bootstrap.md](references/bootstrap.md) — inventory → vocabulary (gate) → instructions (gate) → cards in batches (gate each) → green | One-time, the big spend |
| Large repo bootstrap: draft cards for one domain | [references/cartographer.md](references/cartographer.md) | Per domain |
| "what does this change touch?", "impact of …" | [references/impact.md](references/impact.md) | Small |
| "add a card for <module>" | [references/new-card.md](references/new-card.md) | Small |
| "update the cards for my change", "sync cards" | [references/sync-cards.md](references/sync-cards.md) | Small |
| "I pulled teammates' changes — anything stale?" | [references/catchup.md](references/catchup.md) | Zero tokens until a card needs editing |
| "just write an AGENTS.md" (no full layer) | [references/agents-md.md](references/agents-md.md) | Small |

Card schema and every validation error with its fix: [references/card-format.md](references/card-format.md).
A complete example card and resolve output: [examples/](examples/).

## Rules that keep it alive

1. **Stale metadata is worse than none.** Cards change in the same change as the code they describe.
2. **Humans own the vocabulary and approve every card.** You draft; you never advance past a gate without approval.
3. **Retrieval goes through `kb resolve`.** If the resolved set looks wrong, fix the cards — never work around them.
4. **One fact, one card.** Link by card id instead of duplicating.
5. **Never loosen the tooling** to make an error go away. The strictness is the quality mechanism.
6. Everything you write must be verifiable in the repository: no invented conventions, no guessed invariants. Mark
   anything inferred rather than observed with `(unverified)` for the human reviewer.
