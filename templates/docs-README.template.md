# The Knowledge Layer — how to use it correctly

This folder (plus `scripts/kb/` and `.github/`) is the repo's knowledge
layer: it tells humans and AI agents what each module does, what depends on
what, and which invariants must not be broken — without anyone having to
grep the codebase or hold it all in their head.

It only works if it stays true. This file explains the workflows that keep
it that way.

The knowledge layer is also the substrate for the repo's SemiPilot development
pipeline (refine → critics → plan → implement → scribe): every pipeline stage
retrieves through `kb-resolve` and the scribe maintains the cards. The
pipeline's manual is `INSTRUCTIONS.md` at the repo root; its contract is
`semipilot-core.md`. This file stays the reference for the layer itself.

## The parts

| Piece | What it is |
|---|---|
| `docs/cards/*.md` | One card per module: YAML frontmatter (machine-read) + short prose summary. The unit of knowledge. |
| `docs/cards/_vocabulary.md` | The CLOSED list of tags. The entry point for every lookup. |
| `docs/cards/manifest.json` | Generated index (tags → cards, dependency edges). Committed, never hand-edited. |
| `docs/deep/*.md` | Deep dives a card can point to. Read only when a card sends you there. |
| `scripts/kb/` | Zero-dependency scripts that validate, index, resolve, and drift-check the cards. |
| `.github/copilot-instructions.md` | Always-loaded conventions + the pointer to this system. |
| `.github/instructions/*.instructions.md` | Area rules Copilot loads only when matching files are in play. |
| `.github/prompts/*.prompt.md` | Reusable chat workflows: `/impact`, `/new-card`, `/sync-cards`. |
| `.github/agents/planner.agent.md` | A Copilot agent persona that plans from cards only, never from source. |

## Commands

```
npm run kb:validate                       # cards well-formed, paths exist, edges resolve
npm run kb:index                          # regenerate docs/cards/manifest.json
npm run kb:check                          # fail if the committed manifest is stale
npm run kb:resolve -- --tags <t1,t2>      # tags → the exact files to read
npm run kb:drift                          # real import graph vs declared card edges
git diff --name-only main | npm run kb:guard   # which touched code lacks a card update
```

## Workflow 1 — starting a task (human or AI)

1. Open `docs/cards/_vocabulary.md` and pick the tags that match the task.
   Don't invent tags — if nothing fits, that's a gap to fix (see workflow 4).
2. Run `npm run kb:resolve -- --tags <tags>`. It prints three sections:
   **cards** (read all of them), **deep docs** (read the ones a card makes
   relevant), **code paths** (open only when implementing, per file).
3. Read ONLY what it returned. The whole point is that context stays
   proportional to the task. If the resolved set is missing a module you
   know is involved, stop and fix the card (add the missing `depends_on`
   or tag) — don't quietly work around it, or the layer rots.

In Copilot chat, `/impact` runs this workflow end to end: it proposes tags,
waits for your confirmation, resolves, and produces an impact brief with
open questions before any plan. The `planner` agent enforces the strict
version (cards only, no source reading).

## Workflow 2 — after changing code

The #1 failure mode of systems like this is **stale cards** — confidently
wrong metadata is worse than none. So:

1. If your change touched files under a card's `code:` paths, update that
   card **in the same PR**: contracts, invariants, paths, prose. CI's
   `guard` job nags when you forget (check the step summary).
2. If you changed what a card's frontmatter claims (paths, deps), run
   `npm run kb:validate && npm run kb:index` and commit the regenerated
   manifest — CI blocks on a stale manifest.
3. `npm run kb:drift` tells you if your imports now cross a card boundary
   you didn't declare. Declare the edge or question the import.

In Copilot chat, `/sync-cards` drafts exactly these updates from your diff.

## Workflow 3 — adding a new module

Use `/new-card` in Copilot chat, or by hand: create
`docs/cards/<slug>.md` with id `{{SYSTEM}}.<slug>` (filename must match
the slug), tags from the vocabulary only (one owner per tag — a tag can't
belong to two cards), existing `code:` paths not claimed elsewhere, and a
3–8 sentence prose body. Keep it under 80 lines; depth goes to
`docs/deep/`. Then validate + index + drift as above.

## Workflow 4 — adding a tag

Tags are a closed set on purpose: every lookup starts from them, so an
LLM-invented or ad-hoc tag silently fragments retrieval. Add a tag by
editing `_vocabulary.md` **in a PR**, assign it an owning card in the same
PR, and keep the format `` - `tag` — description `` (the scripts parse it).

## Frontmatter rules (the strict subset)

Cards use a deliberately small YAML subset — `kb-validate` rejects
anything else, which is what keeps the scripts dependency-free:

```yaml
key: value                # scalar ("double-quote" it if it has punctuation)
key: [a, b, c]            # inline list
key:                      # block list
  - item one
  - "item: with punctuation"
```

Allowed keys: `id`, `owns`, `depends_on`, `public_contracts`, `code`,
`docs`, `invariants`. No nested maps, no single quotes, no anchors.

## What NOT to do

- Don't grep the codebase to build context when a resolve would do — and
  don't let an agent do it. Fix the cards instead.
- Don't hand-edit `manifest.json` (regenerate it) or put a `README.md`
  inside `docs/cards/` (every non-underscore `.md` there is parsed as a card).
- Don't duplicate a fact into a second card: one fact lives in exactly one
  card, linked from elsewhere. Duplicates drift apart and an AI reading a
  contradiction picks one at random.
- Don't commit generated graphs. `kb-drift` output is compute-compare-
  discard by design; the manifest is the only committed generated file.
- Don't bypass a `kb-validate` failure by loosening the script — the
  strictness is the quality mechanism.

## Local enforcement — the git pre-commit hook

Instructions are advisory; the hook is the guarantee. `.githooks/pre-commit`
blocks any commit with malformed cards or a stale manifest, and prints the
staleness nag for card-owned code changed without its card. Activate it
**once per clone**:

```
git config core.hooksPath .githooks
```

Since every commit goes through this locally, the knowledge layer cannot
drift silently no matter which tool (Copilot, Claude, or a human) made the
change. Emergency bypass: `git commit --no-verify` — CI will still catch it.

Agents get the same discipline via the "Definition of done" checklist in
`.github/copilot-instructions.md`: kb checks, guard, typecheck, and tests
must pass before a change may be called complete.

## CI (`.github/workflows/knowledge-layer.yml`)

`validate` (blocking): kb-validate + manifest freshness, runs in seconds
with no install. `drift` (warning-only for now via `continue-on-error` —
remove that line once it's been quiet for a while): real imports vs
declared edges. `guard` (never blocks): the staleness nag, in the job's
step summary.

## Troubleshooting

- **"tag X is not in _vocabulary.md"** — use an existing tag or add one
  properly (workflow 4).
- **"code path does not exist"** — the card points at moved/deleted code;
  update the card, then `kb:index`.
- **"manifest.json is stale"** — you changed a card without regenerating:
  `npm run kb:index`, commit the result.
- **DRIFT undeclared dependency X → Y** — real imports cross that boundary;
  add Y to X's `depends_on` (usually right) or remove the import.
- **INFO declared but never imported** — a conceptual edge (e.g. a
  schema card whose files are SQL, never imported). Expected; ignore.
- **kb-drift: "needs the repo's typescript package"** — run `npm install`.
