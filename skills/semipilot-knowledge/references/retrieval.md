# Retrieval — how tags become an exact reading list

## The problem

An agent has two bad default strategies for context: load everything (does not scale, drowns the signal) or search
until something looks relevant (nondeterministic — same task, different context, different answer every run). The
knowledge layer replaces both with a lookup.

## The ladder

| Rung | What | Cost | Gate |
|---|---|---|---|
| L0 | `docs/cards/_vocabulary.md` — skim, pick 1–4 tags | a screen of text | the task |
| L1 | Cards from `kb resolve --tags <tags>` — read in full, they ARE the summary | ~500 tokens per card, typically 5–15 cards | the tags |
| L2 | Deep docs a card lists under `docs:` | only when relevant | a card points there |
| L3 | Code under the cards' `code:` paths | per file, at execution time | a task needs that file |

## What `kb resolve` does

Deterministic, fixed traversal:

1. the cards owning any requested tag;
2. plus **one hop** along `depends_on` and along reverse dependents (who depends on the matched cards);
3. plus those cards' deep docs;
4. code paths printed last, labelled "execution time only".

```
$ python3 scripts/kb/kb.py resolve --tags billing
# kb resolve — tags: billing
# matched: app.billing
# expanded (one hop): app.core

## Read these cards (L1)
docs/cards/billing.md
docs/cards/core.md

## Deep docs if the card points you there (L2)
docs/deep/billing.md

## Code paths — execution time only (L3)
src/billing/  (app.billing)
src/core/  (app.core)
```

`--json` prints the same as JSON for tools. Unknown tags fail with the list of valid ones.

## Why it stays well-defined

- **Every tag has exactly one owning card**, and **every code path has exactly one owning card** (for nested claims
  the longest path wins). `kb validate` rejects violations, so "whose tag / whose file is this" never has two answers.
- `depends_on` edges are declared by hand and **verified** by `kb drift` against the real import graph
  (TypeScript/JavaScript and Python import statements), so the graph `resolve` walks matches the code.
- `kb guard` and `kb catchup` flag cards whose code changed without the card — freshness is enforced, not hoped for.

## In semiPilot's unattended loop

The orchestrator runs `kb resolve` itself with the tags in `requirements.md > Knowledge References` and puts the
reading list into every agent's prompt. No agent needs shell access to retrieve knowledge, and every agent in a run
reads the same set.
