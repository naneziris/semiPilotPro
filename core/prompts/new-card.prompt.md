---
description: "Scaffold a new module card in docs/cards/ that passes kb-validate."
---

Create a new module card for the module I name. Rules — the card must pass
`npm run kb:validate`:

- File: `docs/cards/<slug>.md` where `<slug>` is the last segment of the id.
- Id: `{{SYSTEM}}.<slug>` (lowercase kebab).
- Frontmatter uses ONLY these keys: `id`, `owns`, `depends_on`,
  `public_contracts`, `code`, `docs`, `invariants` — in the strict subset
  syntax: `key: value`, `key: [a, b]`, or a block list of `  - item` lines
  (double quotes when an item contains special punctuation). No nested maps.
- `owns`: tags from `docs/cards/_vocabulary.md` ONLY, and only tags not
  already owned by another card (one owner per tag). If the module needs a
  new tag, add it to `_vocabulary.md` in the same PR and say so.
- `code`: existing repo paths (directories end with `/`). Check that no
  other card already claims the same path — move the claim, don't duplicate.
- `depends_on`: card ids this module imports from or conceptually requires.
  After writing the card, run `npm run kb:drift` and add whatever it reports.
- Prose body: 3–8 sentences — what the module does, boundaries, non-obvious
  behavior. A summary, not a spec; deep detail goes to `docs/deep/`.
- Keep the whole file under 80 lines.

Then run: `npm run kb:validate && npm run kb:index && npm run kb:drift`
and include the regenerated `docs/cards/manifest.json` in the change.
