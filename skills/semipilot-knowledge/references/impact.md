# Impact analysis for a change

Follow these steps IN ORDER. Do not skip the confirmation, and do not read files outside the resolved set.

1. **Propose tags.** Read `docs/cards/_vocabulary.md`. From the CLOSED list only, propose the 1–4 tags matching the
   change, one line of reasoning each, and **ask the user to confirm**. Never invent a tag; if nothing fits, say so
   and stop.
2. **Resolve.** After confirmation: `python3 scripts/kb/kb.py resolve --tags <confirmed,tags>`.
3. **Read the resolved set only.** The cards (L1) in full; deep docs (L2) a card makes relevant. Do NOT open code
   (L3) yet and do NOT search the codebase for extra context. If the set seems to miss a module, say so — the fix is
   a card, not a workaround.
4. **Impact brief:**
   - touched cards and why; public contracts at risk (from `public_contracts:`);
   - invariants that constrain the change (quote the card lines);
   - cross-cutting trigger implications (from the instructions file's *Cross-cutting triggers*);
   - open questions the user must answer before implementation.
   Wait for the answers.
5. **Plan** (only after the answers): steps with concrete files (from the cards' `code:` paths), the tests to add or
   update, and which cards must change in the same change.

For a full feature with acceptance criteria and an unattended build, use the `semipilot-refine` skill instead — it
runs this analysis as its step 5.
