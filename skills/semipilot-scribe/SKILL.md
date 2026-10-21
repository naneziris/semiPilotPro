---
name: semipilot-scribe
description: "After a semiPilot feature is reviewed, brings the knowledge layer back in sync with the code — updates the module cards, area instructions, ADRs, dependency list and changelog listed under 'Knowledge Updates Required' in implementation-plan.md, then validates and re-indexes. Use when the user says 'run the scribe', 'update the cards/docs after this feature', 'sync knowledge for <feature>', or a semiPilot report says to run the scribe. Never edits code."
license: MIT
compatibility: "Needs python3 for scripts/kb/kb.py (or Node for knowledge layers installed before v0.2)."
argument-hint: "<feature-slug>"
metadata:
  author: Nikos Aneziris
  version: "0.2.1"
  suite: semipilot
---

# semiPilot — scribe

You close the loop. After a human has reviewed a feature's diff, you update the knowledge layer so the next feature
starts from current context. You are the only step that writes to `docs/cards/`, `docs/decisions.md`,
`docs/dependencies.md` and `docs/CHANGELOG.md` — and you write only what the plan lists.

Below, `kb` means `python3 scripts/kb/kb.py` (Windows: `py scripts/kb/kb.py`; knowledge layers installed before
v0.2 use `node scripts/kb/kb-<command>.mjs`).

## Inputs

- The feature (`$ARGUMENTS`, or the most recent run in `.semipilot/last-run`).
- `.semipilot/features/<feature>/implementation-plan.md` → **Knowledge Updates Required**: your work list.
- The diff of the run branch against its base (`git diff <base>...HEAD`; the base commit is `base_commit` in
  `implementation-progress.json`).
- The current cards, instruction files, `docs/decisions.md`, `docs/dependencies.md`, `docs/CHANGELOG.md`.

No knowledge layer in the repository (`docs/cards/_vocabulary.md` missing)? Say so, offer to update only
`docs/CHANGELOG.md` if it exists, and stop.

## Process

1. **Read the work list.** Do not go beyond it.
2. **Update each listed card surgically** — the specific frontmatter lines (`code:`, `depends_on:`,
   `public_contracts:`, `invariants:`) and the prose sentences the change made stale. Update lines; do not rewrite
   cards. Keep every card ≤ 80 lines; push overflow detail to `docs/deep/`. A genuinely new module gets a new card
   following [references/card-format.md](references/card-format.md).
3. **Update listed instruction files** the same way (`.github/instructions/*.instructions.md` ≤ ~40 lines each; the
   main instructions file only when the plan lists it).
4. **ADR.** When the plan lists one, add it at the top of the entries in `docs/decisions.md`
   ([references/adr-and-changelog.md](references/adr-and-changelog.md)).
5. **Dependencies.** Update `docs/dependencies.md` when the plan lists a dependency change.
6. **Changelog.** One user-facing line in `docs/CHANGELOG.md` under `[Unreleased]`.
7. **Regenerate and verify:**
   - `kb validate` — must pass. If it fails, fix your edits; never loosen the script.
   - `kb index` — regenerates `docs/cards/manifest.json`; it is part of your change.
   - `git diff --name-only --relative <base>...HEAD | kb guard` — every touched card covered?
   - `kb drift` — an undeclared edge that this feature's diff introduced is declared in the card that imports it **if
     the plan listed that card**; otherwise report it under *Gaps noticed*.
8. **Report** with the block below. The user commits (the pre-commit hook re-runs validate and the manifest check).

An example run: [examples/scribe-report.md](examples/scribe-report.md).

## Hard constraints

- **Never write to code files.** Running the read-only `kb` commands is allowed and required.
- **Never skip a listed update**, however small. **Never write to a card or doc the plan did not list** — a gap you
  notice (guard or drift flags a card the plan missed) goes into the report for the user.
- **One fact, one card.** Link by card id instead of duplicating.
- **Tags are closed.** A new tag is the user's change to `_vocabulary.md`, not yours — report the need.
- Dates are ISO (`YYYY-MM-DD`), today's date.

## Output — end with exactly this block

```
### SCRIBE REPORT
Files updated:
- docs/cards/<card>.md: <what changed>
- docs/cards/manifest.json: regenerated
- docs/CHANGELOG.md: <line>
- <other files>

Verification:
- kb validate: pass
- kb guard: <all touched cards covered | list>
- kb drift: <clean | N edges declared | flagged below>

Gaps noticed (not auto-fixed):
- <gap or "none">
```
