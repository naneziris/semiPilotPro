---
description: "Impact analysis for a requirement: tags → kb-resolve → impact brief. Run before planning any non-trivial change."
---

You are doing impact analysis for a requirement in this repo. Follow these
steps IN ORDER. Do not skip the human confirmation, and do not read files
outside the resolved set.

1. **Propose tags.** Read `docs/cards/_vocabulary.md`. From the CLOSED tag
   list only, propose the tags matching the requirement (typically 1–4).
   Show them to me with one line of reasoning each and ASK ME TO CONFIRM
   before continuing. Never invent a tag; if nothing fits, say so and stop.

2. **Resolve.** After I confirm, run in the terminal:
   `npm run kb:resolve -- --tags <confirmed,tags>`

3. **Read the resolved set only.** Read the cards (L1) it lists, and any
   deep doc (L2) a card points to that is relevant. Do NOT open code (L3)
   yet, and do NOT grep or search the codebase for extra context. If the
   resolved set seems to miss a module, tell me — the fix is a card fix,
   not a workaround.

4. **Impact brief.** Produce:
   - Touched cards and why; public contracts at risk (from `public_contracts:`)
   - Invariants that constrain the change (quote the card lines)
   - Cross-cutting trigger implications (per the `Cross-cutting triggers`
     section of `.github/copilot-instructions.md`)
   - Open questions I must answer before implementation
   Wait for my answers to the open questions.

5. **Plan.** Only after my answers: a step-by-step implementation plan with
   concrete files (from the cards' `code:` paths), the tests to add or
   update, and which cards need updating in the same PR.
