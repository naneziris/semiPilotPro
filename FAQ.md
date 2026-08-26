# FAQ

Practical answers for day-to-day use of the knowledge layer. Deeper context:
`USAGE.md` (daily flow), `INSTALL.md` (setup and solo/POC mode).

---

## What steps do I take when I pull or fetch new changes?

1. **`npm run kb:catchup`** — zero tokens. It diffs your personal baseline
   (stored in `.git/kb-last-sync`, never shared) against the new HEAD and
   lists any cards whose owned code teammates changed without touching the
   card.
2. **If nothing is flagged — you're done.** Optionally run
   `npm run kb:validate && npm run kb:drift` for a deeper check, then move
   the baseline: `npm run kb:catchup -- --mark`.
3. **If cards are flagged**, per flagged card:
   - Skim the actual diff: `git diff <baseline>...HEAD -- <the listed files>`
   - Update the card — by hand (free) or via `/sync-cards` in Copilot chat
     with the printed file list (small, card-scoped token cost)
   - Regenerate and verify:
     `npm run kb:index && npm run kb:validate && npm run kb:drift`
   - Move the baseline: `npm run kb:catchup -- --mark`

## Why does `kb:catchup` say "no baseline yet" the first time?

The baseline is personal and local, so it starts unset. Run
`npm run kb:catchup -- --mark` once, at a moment when the cards are true
(e.g. right after the bootstrap, or after reviewing them). From then on,
every catchup reports only what changed after that point.

## `kb:catchup` says my baseline "no longer exists" — what happened?

The baseline commit was rewritten away (rebase) or garbage-collected.
Nothing is broken: review the cards against the current state if in doubt,
then set a fresh baseline with `npm run kb:catchup -- --mark`.

## I forgot to run `--mark` after catching up. Is anything corrupted?

No. The next `kb:catchup` simply re-reports everything since the old
baseline — noisy, but harmless. Re-check (or recognize) the already-handled
cards and `--mark` to silence it. The mark is deliberately manual so a range
is never skipped without someone having actually looked at it.

## Can I trial the kit in a shared repo without committing anything?

Yes — install it, use it, and keep it out of the team's way until you're
convinced. Three things make this safe:

1. **Ignore the kit files locally, not in the shared `.gitignore`.** Add the
   installed paths to `.git/info/exclude` (same syntax as `.gitignore`, but
   local-only and never committed), e.g.:

   ```
   scripts/kb/
   docs/cards/
   docs/README.md
   docs/decisions.md
   docs/dependencies.md
   docs/CHANGELOG.md
   .githooks/
   .github/prompts/
   .github/agents/
   .github/skills/
   .github/workflows/knowledge-layer.yml
   .github/copilot-instructions.md
   .vscode/settings.json
   AGENTS.md
   ```

   This keeps `git status` clean and makes an accidental `git add .`
   impossible.
2. **Back up the cards.** Untracked files have no history and no remote:
   a `git clean -fd` deletes them all, and the bootstrap that produced them
   was the expensive one-time token spend. Either commit the kit to a
   private local branch you never push, or copy `docs/cards/` somewhere
   safe periodically.
3. **Know the one degraded behavior:** `kb:catchup` detects "teammate
   changed code without updating the card" via git diffs. While your cards
   are untracked they never appear in any diff, so the "card was already
   updated in this range" suppression can't trigger — flagged cards stay
   flagged until you `--mark`. Everything else (validate, index, resolve,
   drift, guard, the pre-commit hook) works purely off the filesystem and
   behaves normally.

When the trial convinces you: delete the `.git/info/exclude` entries,
commit everything, and push — the hook config (`git config core.hooksPath
.githooks`) is the only per-clone step teammates need.

## Does any of this send data anywhere?

No. Every `kb:*` script, the hook, and the installer are deterministic,
local-only Node/shell — no network calls, no telemetry. The only things
that cost tokens (and talk to a model) are the chat prompts and agents you
invoke explicitly, through your own Copilot/agent setup.
