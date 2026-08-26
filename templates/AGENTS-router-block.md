<!-- Append this block to the target repo's AGENTS.md (create the file with
     just this block if it doesn't exist). Never maintain two divergent
     routers: AGENTS.md points at copilot-instructions.md, full stop. -->

# Repo knowledge router

Repo conventions and invariants: `.github/copilot-instructions.md` (single
source of truth — this file only points there). Module knowledge: one card
per module in `docs/cards/`; pick tags from `docs/cards/_vocabulary.md` and
run `npm run kb:resolve -- --tags <t1,t2>`, then read only the files it
returns instead of grepping the codebase.

Workflow playbooks live in `.github/prompts/*.prompt.md`. In VS Code Copilot
chat they are slash commands (`/sync-cards`, `/impact`, `/run-pipeline`, …).
In agents without prompt-file support (Copilot CLI, Claude Code, …): when
the user asks to run one of these workflows — sync/update the cards, run an
impact analysis, run the pipeline, refine requirements, bootstrap the
knowledge layer — read the matching `.prompt.md` and execute it as your
instructions for that task.
