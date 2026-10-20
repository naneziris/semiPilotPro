# Sync the cards with a change

The user just implemented a change. Bring the knowledge layer in sync with it — minimal, card-scoped edits.

1. Find the cards that own touched code:
   `git diff --name-only --relative <base>...HEAD | python3 scripts/kb/kb.py guard`
   (`<base>` is usually `main`; for uncommitted work use `git diff --name-only --relative HEAD`, or pass files with
   `--files`).
2. For each flagged card, compare the diff with the card's frontmatter and prose: new or removed code paths, changed
   public contracts, new or obsolete invariants, changed dependencies. Also check whether an
   `.github/instructions/*.instructions.md` file or the main instructions file now states something false.
3. Draft the minimal edits — update lines, don't rewrite cards. A genuinely new module → [new-card.md](new-card.md).
4. `kb validate && kb index && kb drift`, include the regenerated manifest. A new undeclared edge → declare it, or
   question the import.
5. List anything you did NOT update and why, so the user can double-check.

After a semiPilot run, prefer the `semipilot-scribe` skill: it works from the planner's *Knowledge Updates Required*
list instead of rediscovering it.
