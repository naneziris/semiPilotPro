# Add a card for a new module

The card must pass `kb validate`. Schema and errors: [card-format.md](card-format.md).

- File `docs/cards/<slug>.md`, id `<system>.<slug>` (lowercase kebab; `<system>` = the prefix the other cards use).
- `owns`: tags from `docs/cards/_vocabulary.md` ONLY, and only tags no other card owns. If the module needs a new
  tag, propose the vocabulary line to the user — they add it in the same change.
- `code`: existing paths (directories end with `/`), not claimed by another card — move a claim rather than
  duplicating it.
- `depends_on`: card ids this module imports from or conceptually requires. After writing, run `kb drift` and add
  whatever it reports for this card.
- Prose: 3–8 sentences — what it does, its boundaries, non-obvious behaviour. Deep detail goes to `docs/deep/`.
- ≤ 80 lines.

Then run `python3 scripts/kb/kb.py validate && python3 scripts/kb/kb.py index && python3 scripts/kb/kb.py drift` and
include the regenerated `docs/cards/manifest.json` in the change.
