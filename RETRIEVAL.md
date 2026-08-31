# Retrieval — how progressive disclosure finds the right files

This document explains the mechanism that decides which files an agent (or a
human) reads for a given task: the cards, the closed vocabulary, the manifest,
and the `kb-resolve` walk that turns a couple of tags into an exact reading
list. `docs/README.md` (installed from `templates/docs-README.template.md`) is
the day-to-day manual; this is the "how does it actually work" reference.

## The problem it solves

An AI agent has two bad default strategies for building context: load
everything (doesn't scale, drowns the signal) or grep around until something
looks relevant (nondeterministic — same task, different context, different
answer every run). The knowledge layer replaces both with a lookup: context is
**resolved**, not searched. Same input, same file set, every time. That
determinism is what makes impact analysis auditable and lets the critics check
a spec's card list against a reproducible ground truth.

## The pieces

| Piece | Role in retrieval |
|---|---|
| `docs/cards/_vocabulary.md` | The CLOSED tag list — the only entry point. Every lookup starts by picking tags from it. Parsed mechanically: a tag is a line matching `` - `tag` `` (lowercase, digits, hyphens). New tags enter by PR only. |
| `docs/cards/<module>.md` | One card per module — the unit of knowledge. Machine-read YAML frontmatter + ≤80 lines total with a short prose summary. |
| `docs/cards/manifest.json` | Generated index (`npm run kb:index`): tags → owning cards, per-card metadata, dependency edges. Committed, never hand-edited. |
| `docs/deep/*.md` | Depth a card can point to via `docs:`. Read only when a card sends you there. |
| The codebase | The last rung. Opened per-file at execution time, never for orientation. |

### What a card's frontmatter contributes

```yaml
id: yourapp.sync-cloud        # <system>.<module>, must match the filename stem
owns: [sync, cloud-backup]    # tags this card answers for — each tag has exactly ONE owner
depends_on: [yourapp.auth]    # card ids this module requires — the graph kb-resolve walks
public_contracts:             # what can break outsiders: APIs, schemas, events, persisted shapes
  - "SyncEnvelope v2 (schema in src/lib/types.ts)"
code:                         # repo paths this card owns (dirs end with /)
  - src/lib/sync/
docs:                         # optional deep dives (the L2 rung)
  - docs/deep/sync-conflict-resolution.md
invariants:                   # "know this or you'll write a bug" — quotable single lines
  - "Never write to the envelope store outside applyEnvelope()"
```

Two structural rules make retrieval well-defined: **every tag has exactly one
owning card** (`kb-validate` rejects a second owner), and **every code path has
exactly one owning card** (duplicate claims are rejected; for nested claims the
longest path wins, so a card may own a subtree inside another card's
directory). There is never ambiguity about "whose file is this" or "whose tag
is this".

## The disclosure ladder

Context is loaded in rungs, and each rung is gated by the one above it:

- **L0 — vocabulary.** A skim of the tag list (~a screen of text). Output: 1–4
  tags describing the task.
- **L1 — cards.** `kb-resolve` turns those tags into a card set (~500 tokens
  per card, typically 5–15 cards). Cards are always read in full — they ARE
  the summary.
- **L2 — deep docs.** Only the deep docs linked by the resolved cards, and only
  when the card's subject matches an actual task concern.
- **L3 — code.** The resolved cards' `code:` paths, printed as pointers.
  Opened per-file while implementing — never "read the module to get an
  overview" (that is what the card was for).

Cost scales with the task, not the codebase: a small change resolves a small
set, no matter how big the repo is. The pipeline's agents live on this ladder
(the refiner, planner, and critics work almost entirely at L1, verifying
specifics at L3 only inside the resolved cards' paths), and the conventions
corpus (`.github/copilot-instructions.md` + `applyTo`-scoped instructions
files) rides alongside it through Copilot's own loading mechanism.

## The resolve walk — exactly what `kb-resolve` does

`npm run kb:resolve -- --tags sync,cloud-backup` performs a fixed traversal:

1. **Validate the tags.** Every requested tag must exist in
   `_vocabulary.md`; an unknown tag is a hard error listing the valid set.
   (This is why the vocabulary is closed — an invented tag would silently
   resolve to nothing.)
2. **Match owners.** Collect every card whose `owns:` includes any requested
   tag. Zero matches is a hard error, not an empty success.
3. **Expand one hop, both directions.** Add each matched card's `depends_on`
   targets (what it needs) AND every card that depends on a matched card (who
   needs it — the reverse edge is what surfaces consumers you'd forget). One
   hop only: the graph does not close transitively, which keeps the set
   proportional to the task. If something two hops away genuinely matters, the
   intermediate card's own frontmatter is where that edge belongs.
4. **Emit the ladder.** Three sections, in disclosure order:
   `## Read these cards (L1)` — the expanded card set, sorted;
   `## Deep docs if the card points you there (L2)` — the union of the set's
   `docs:` links; `## Code paths — execution time only (L3)` — each card's
   `code:` claims, labeled with the owning card id.

The output also names which cards were direct matches vs. one-hop expansions,
so a reviewer can see WHY each file is in the set. Determinism falls out of
the design: closed vocabulary, single ownership, fixed traversal, sorted
output — same tags, same list, every run.

## What the manifest is for (and what it is not)

`npm run kb:index` regenerates `docs/cards/manifest.json` from the cards: a
`tags` map (tag → owning card ids), a `cards` index (file, owns, code, docs,
depends_on per card), and the flattened `edges` list. Keys are recursively
sorted so the file only changes when the cards change, keeping PR diffs
meaningful.

Note what is NOT true: `kb-resolve` does not read the manifest — it parses the
card files directly, so retrieval can never be poisoned by a stale index. The
manifest exists for everything AROUND retrieval: it is the machine-readable
snapshot of the layer for CI and external consumers (e.g. a cross-repo
contract registry), and its staleness check (`npm run kb:check`, enforced by
the pre-commit hook and CI) is the cheap signal that someone changed cards
without regenerating. It is the only committed generated artifact; anything
bigger (drift graphs) is compute-compare-discard.

## How files map back to cards (the reverse lookup)

Retrieval answers "task → files"; the guard rail needs the inverse, "changed
file → owning card". `buildClaims` flattens every card's `code:` entries into
a claims table sorted longest-path-first; `ownerOf` walks it and the first
(longest) match wins. `kb-guard` uses this to nag when a commit touches
card-owned code without touching the card, and Gate 2's knowledge-coverage
check uses the same mapping to reject a plan that omits a flagged card.

## What keeps the resolved set truthful

A lookup is only as good as its index. Four mechanisms, all deterministic:

- **`kb-validate`** — referential integrity: frontmatter subset only, ids
  well-formed and matching filenames, tags from the vocabulary with one owner
  each, `code:`/`docs:` paths that exist, `depends_on` ids that resolve, no
  duplicate claims, non-empty prose. Every pipeline entry point runs it first
  and refuses to work on an unhealthy layer.
- **`kb-drift`** — compares the REAL import graph (parsed from source) against
  the declared `depends_on` edges and reports undeclared or stale edges, so
  the graph `kb-resolve` walks cannot quietly diverge from reality.
- **`kb-guard`** + the pre-commit hook and CI — catch code changes that leave
  their card behind.
- **`@scribe`** — inside the pipeline, the only writer of cards: after Gate 2
  approves a diff, it applies the plan's Knowledge Updates and re-runs the
  suite above, so the next cycle resolves against current knowledge.

## The operating rules

Retrieval only via `kb-resolve` — no repo-wide grepping for context, by human
or agent. If the resolved set looks wrong (a module you know is involved is
missing), the fix is ALWAYS a card fix — add the missing tag, `depends_on`
edge, or card — never a silent workaround, because a workaround leaves the
next lookup just as wrong. And tags are added by PR to `_vocabulary.md`, never
invented mid-task: the vocabulary is written in the team's real language, and
every downstream classification inherits it.
