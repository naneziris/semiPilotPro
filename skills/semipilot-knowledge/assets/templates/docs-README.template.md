# The knowledge layer — how to use it

This folder (plus `scripts/kb/`, `AGENTS.md` and `.github/instructions/`) is {{REPO_NAME}}'s knowledge layer: it
tells humans and AI agents what each module does, what depends on what, and which invariants must not be broken —
without anyone grepping the codebase or holding it all in their head. It only works if it stays true; this file
explains the workflows that keep it that way.

## The parts

| Piece | What it is |
|---|---|
| `docs/cards/*.md` | One card per module: strict frontmatter (machine-read) + a short prose summary. The unit of knowledge. |
| `docs/cards/_vocabulary.md` | The CLOSED list of tags — the entry point for every lookup. |
| `docs/cards/manifest.json` | Generated index (tags → cards, dependency edges). Committed, never hand-edited. |
| `docs/deep/*.md` | Deep dives a card can point to. Read only when a card sends you there. |
| `scripts/kb/kb.py` | Standard-library Python: validate, index, resolve, drift, guard, catchup. |
| `AGENTS.md` | Always-loaded instructions for every agent, ending with the knowledge router. |
| `.github/instructions/*.instructions.md` | Area rules, loaded by Copilot when matching files are in play and read by other agents on instruction. |
| `docs/decisions.md`, `docs/dependencies.md`, `docs/CHANGELOG.md` | ADRs, dependency policy, user-facing changelog. |

## Commands

```
python3 scripts/kb/kb.py validate                    # cards well-formed, paths exist, edges resolve
python3 scripts/kb/kb.py index                       # regenerate docs/cards/manifest.json
python3 scripts/kb/kb.py index --check               # fail if the committed manifest is stale
python3 scripts/kb/kb.py resolve --tags <t1,t2>      # tags → the exact files to read
python3 scripts/kb/kb.py drift                       # real import graph vs declared card edges
git diff --name-only --relative main | python3 scripts/kb/kb.py guard   # touched code without a card update
python3 scripts/kb/kb.py catchup [--mark]            # cards teammates' changes made stale since your baseline
```

(Windows: `py` instead of `python3`. With the semipilot CLI: `semipilot kb <command>`.)

## Workflow 1 — starting a task (human or agent)

1. Pick the tags that match the task from `docs/cards/_vocabulary.md`. Don't invent tags (see workflow 4).
2. `python3 scripts/kb/kb.py resolve --tags <tags>` prints **cards** (read all), **deep docs** (read the relevant
   ones) and **code paths** (open only when implementing).
3. Read ONLY what it returned. If a module you know is involved is missing, fix the card (a missing `depends_on` or
   tag) — don't quietly work around it, or the layer rots.

In agent chat, the `semipilot-knowledge` skill's *impact* workflow does this end to end, and semiPilot's
`semipilot-refine` skill does it as part of writing requirements.

## Workflow 2 — after changing code

Stale cards are the #1 failure mode — confidently wrong metadata is worse than none.

1. Touched files under a card's `code:` paths? Update that card **in the same change**: contracts, invariants,
   paths, prose. The `guard` nag (hook and CI) reminds you.
2. Changed what a card's frontmatter claims? `validate` and `index`, commit the regenerated manifest (CI blocks a
   stale one).
3. `drift` tells you when your imports now cross a card boundary you didn't declare. Declare it, or question the import.

After a semiPilot run, the `semipilot-scribe` skill does this from the planner's *Knowledge Updates Required* list.

## Workflow 3 — adding a module

`docs/cards/<slug>.md` with id `{{SYSTEM}}.<slug>` (file name must match), tags from the vocabulary only (one owner
per tag), existing `code:` paths not claimed elsewhere, a 3–8 sentence summary, ≤ 80 lines. Then validate, index,
drift.

## Workflow 4 — adding a tag

Tags are closed on purpose: every lookup starts from them, so an ad-hoc tag silently fragments retrieval. Add one by
editing `_vocabulary.md` in a reviewed change, give it an owning card in the same change, and keep the format
`` - `tag` — description ``.

## Frontmatter rules (the strict subset)

```yaml
key: value                # scalar ("double-quote" it if it has punctuation)
key: [a, b, c]            # inline list
key:                      # block list
  - item one
  - "item: with punctuation"
```

Allowed keys: `id`, `owns`, `depends_on`, `public_contracts`, `code`, `docs`, `invariants`. No nested maps, no single
quotes, no anchors.

## What NOT to do

- Don't search the codebase for context when a resolve would do — and don't let an agent do it. Fix the cards.
- Don't hand-edit `manifest.json`, and don't put a `README.md` inside `docs/cards/` (every non-underscore `.md`
  there is parsed as a card).
- Don't duplicate a fact into a second card: one fact, one card, linked by id.
- Don't commit generated graphs: `drift` is compute-compare-discard by design; the manifest is the only committed
  generated file.
- Don't bypass a `validate` failure by loosening the script — the strictness is the quality mechanism.

## Enforcement

- **Pre-commit hook** (`.githooks/pre-commit`): blocks malformed cards and a stale manifest; prints the staleness
  nag. Activate once per clone: `git config core.hooksPath .githooks`. Bypass in an emergency with `--no-verify`.
- **CI** (`.github/workflows/knowledge-layer.yml`): `validate` (blocking), `drift` (warning-only until quiet —
  then remove `continue-on-error`), `guard` (never blocks; nags in the step summary).

## Troubleshooting

- **tag X is not in _vocabulary.md** — use an existing tag or add one properly (workflow 4).
- **code path does not exist** — the card points at moved or deleted code; update it, then `index`.
- **manifest.json is stale** — `python3 scripts/kb/kb.py index`, commit the result.
- **DRIFT undeclared dependency X → Y** — add Y to X's `depends_on` (usually right) or remove the import.
- **INFO declared but never imported** — a conceptual edge (e.g. a schema card whose files are SQL). Expected.
- **drift finds no source files** — set `srcDirs`, `aliases` and `extensions` in `scripts/kb/kb.config.json`.
