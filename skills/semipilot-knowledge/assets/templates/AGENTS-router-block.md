
<!-- semipilot:knowledge-router (appended by `semipilot kb init`; keep it at the end of this file) -->
## Knowledge layer — how to find module knowledge

Module knowledge lives in `docs/cards/`, one card per module. Do NOT search the whole codebase to build context.
Pick 1–4 tags from `docs/cards/_vocabulary.md` (a closed list), run
`python3 scripts/kb/kb.py resolve --tags <t1,t2>` (Windows: `py scripts/kb/kb.py …`) and read only what it returns:
the cards in full, the deep docs a card points you to, and code only inside the listed paths when you implement.
Honor every card's `invariants:` and `public_contracts:`. If the resolved set looks wrong, fix the cards — never
work around them.

Area rules live in `.github/instructions/*.instructions.md`; read the ones whose `applyTo` matches the files you
change (GitHub Copilot loads them automatically).

When your change touches files under a card's `code:` paths, update that card in the same change and run
`python3 scripts/kb/kb.py validate && python3 scripts/kb/kb.py index` (the pre-commit hook and CI enforce it).
Workflows (bootstrap, impact analysis, new card, sync cards, catch-up) are in the `semipilot-knowledge` skill.
