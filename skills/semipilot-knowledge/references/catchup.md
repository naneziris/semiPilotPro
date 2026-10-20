# Catch up after pulling teammates' changes

For teams where not everyone maintains the cards yet (solo / pilot mode). Detection is fully deterministic and
costs zero tokens; only editing a flagged card involves you.

1. `python3 scripts/kb/kb.py catchup` — diffs the user's personal baseline (`.git/kb-last-sync`, never committed or
   shared) against HEAD and lists cards whose owned code changed without the card.
   - "no baseline yet": run `kb catchup --mark` once, at a moment when the cards are true (right after bootstrap or
     a review).
   - "baseline no longer exists": it was rebased or garbage-collected; review if in doubt, then `--mark` again.
2. Nothing flagged → optionally `kb validate && kb drift`, then `kb catchup --mark`. Done.
3. Flagged cards → for each: skim `git diff <baseline>...HEAD -- <listed files>`, update the card per
   [sync-cards.md](sync-cards.md) step 2–3, then `kb index && kb validate && kb drift`.
4. Move the baseline: `kb catchup --mark`.

Forgot `--mark`? Nothing is corrupted; the next catchup re-reports the same range.
