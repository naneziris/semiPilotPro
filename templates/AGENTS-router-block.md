<!-- Append this block to the target repo's AGENTS.md (create the file with
     just this block if it doesn't exist). Never maintain two divergent
     routers: AGENTS.md points at copilot-instructions.md, full stop. -->

# Repo knowledge router

Repo conventions and invariants: `.github/copilot-instructions.md` (single
source of truth — this file only points there). Module knowledge: one card
per module in `docs/cards/`; pick tags from `docs/cards/_vocabulary.md` and
run `npm run kb:resolve -- --tags <t1,t2>`, then read only the files it
returns instead of grepping the codebase.
