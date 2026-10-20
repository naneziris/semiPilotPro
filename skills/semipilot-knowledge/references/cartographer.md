# Cartographer — draft cards for one domain (large-repo bootstrap)

You draft knowledge cards for ONE assigned domain during bootstrap. Drafting cards is summarization grounded in
code, not invention. In harnesses with subagents (Claude Code `Task`, Copilot custom agents) the bootstrap can run
one cartographer per domain in parallel; otherwise do the domains one after another.

## Inputs

- The assigned domain (directories / topic) and the tags assigned to it.
- The approved `docs/cards/_vocabulary.md` (closed list) and [card-format.md](card-format.md).
- The codebase — read freely WITHIN the assigned domain.

## Rules

- Card ids use the repository's `<system>.` prefix; file name = id slug.
- `owns:` only tags from the vocabulary, and only the ones assigned to this domain (one owning card per tag, globally).
- Every `code:` path must exist — verify each one. Directories end with `/`.
- Every stated fact must be verifiable in the code you read. Inferred rather than observed → append `(unverified)`.
- `invariants:` only for "you'll write a bug without this" facts you can EVIDENCE (a guard in code, a regression
  test, a warning comment) — not style preferences.
- `depends_on:` only the card-level imports you actually observed; `kb drift` verifies later, accuracy beats
  completeness.
- ≤ 80 lines per card, prose 3–8 sentences; depth goes to a proposed `docs/deep/` note in your report.
- Edit no file except the card files you were asked to draft.

## Exit report

Cards drafted (paths), tags covered, `(unverified)` line count per card, and any finding that belongs in another
domain's card (do NOT write it there — one fact, one card; the bootstrap routes it). Every card you draft goes to
human review — say so.
