---
id: {{SYSTEM}}.{{TODO: slug — must equal the filename stem}}
owns: [{{TODO: tags from _vocabulary.md — each tag has exactly ONE owning card}}]
depends_on: [{{TODO: card ids this module imports from or conceptually requires — kb-drift verifies}}]
public_contracts:
  - "{{TODO: things whose change can break someone outside this module — APIs, schemas, persisted shapes, events}}"
code:
  - {{TODO: repo paths this card owns — directories end with /; no path may be claimed by two cards (longest claim wins for subtrees)}}
docs:
  - {{TODO: docs/deep/<file>.md — optional, only if a deep doc exists}}
invariants:
  - {{TODO: "you must know this or you'll write a bug" facts — quotable single lines}}
---
{{TODO: 3–8 sentences of prose. What the module does, its boundaries, its
non-obvious behaviors. A summary, not a spec — depth goes in docs/deep/.
Whole card ≤ 80 lines. One fact lives in exactly one card; reference other
modules by card id instead of duplicating.}}
