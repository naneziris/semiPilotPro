# Card format (what `kb validate` enforces)

A card is `docs/cards/<slug>.md`: strict frontmatter plus a short prose summary. Every non-underscore `.md` in
`docs/cards/` is parsed as a card.

```markdown
---
id: <system>.<slug>              # lowercase kebab, <system>.<module>; <slug> == the file name stem
owns: [tag-a, tag-b]             # tags from docs/cards/_vocabulary.md ONLY; each tag has exactly one owning card
depends_on: [<system>.other]     # card ids this module imports from or conceptually requires (kb drift verifies)
public_contracts:
  - "Things whose change breaks someone outside: APIs, schemas, persisted shapes, events"
code:
  - src/billing/                 # paths this card owns; directories end with /; one owner per path (longest wins)
docs:
  - docs/deep/billing-rounding.md   # optional deep dives
invariants:
  - "Know this or you will write a bug — quotable, one line, evidenced in code or tests"
---
3–8 sentences: what the module does, its boundaries, its non-obvious behaviour. A summary, not a spec.
```

## The frontmatter subset

`key: value` · `key: [a, b]` · a block list of `  - item` lines (two spaces). Double-quote an item that contains
punctuation like `:` or `,`. No nested maps, no single quotes, no anchors. Allowed keys: `id`, `owns`,
`depends_on`, `public_contracts`, `code`, `docs`, `invariants`. Anything else is an error — that strictness is what
keeps the tooling dependency-free and the cards machine-simple.

## Validation errors you may hit

| Error | Fix |
|---|---|
| `tag "x" is not in _vocabulary.md` | Use an existing tag, or report that a new tag is needed |
| `tag "x" already owned by …` | One owner per tag: move it, or use a different tag |
| `code path does not exist` | The code moved: update the path |
| `code path … already claimed by …` | One owner per path: claim a narrower subtree or move the claim |
| `depends_on "…" does not resolve` | Typo in a card id, or the card was removed |
| `filename must be "<slug>.md"` | Rename the file or fix the id |
| `prose body is empty` | Write the 3–8 sentence summary |
| `manifest.json is stale` | Run `kb index` and include the result |
