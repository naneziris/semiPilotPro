---
description: "After implementing a change: find and draft the knowledge-layer updates it requires."
---

I just implemented a change. Bring the knowledge layer in sync with it:

1. Run `git diff --name-only main...HEAD | npm run kb:guard` (or pass the
   changed files with `--files`) to see which cards own touched code.
2. For each flagged card, compare the diff against the card's frontmatter
   and prose: new/removed code paths, changed public contracts, new or
   obsolete invariants, changed dependencies. Also check whether any
   `.github/instructions/*.instructions.md` file states something the
   change made false.
3. Draft the minimal card/instruction edits — update lines, don't rewrite
   whole cards. If the change added a genuinely new module, use
   `.github/prompts/new-card.prompt.md` instead.
4. Run `npm run kb:validate && npm run kb:index && npm run kb:drift` and
   include the regenerated manifest. If drift reports a new undeclared
   edge, declare it or question the import.
5. List anything you did NOT update and why, so I can double-check.
