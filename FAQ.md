# FAQ

Practical answers for day-to-day use of the knowledge layer. Deeper context:
`USAGE.md` (daily flow), `INSTALL.md` (setup and solo/POC mode).

---

## How do I start a task — `/run-pipeline`, `/refine-requirements`, or `@refiner`?

All three are valid doors into the same flow; pick by how much routing you
want to do yourself:

- **`/run-pipeline <idea>`** (VS Code chat) — the one-command entry. It
  runs the entire flow (refine → Gate 1 → plan → implement → Gate 2 →
  scribe), invoking each stage as a subagent and routing on their
  `### HANDOFF:` blocks automatically. It pauses only where a human
  belongs: tag confirmation, clarifying questions, and the two gates.
  **If in doubt, start here.**
- **`/refine-requirements <idea>`, then follow the handoffs** — manual
  mode. Each stage ends with a `### HANDOFF:` block naming exactly what to
  invoke next (`@spec-critic`, `/create-implementation-plan`,
  `/implement-plan`, `@pattern-critic`, `@scribe`); you are the router.
  Use this to enter mid-pipeline or inspect between stages.
- **`@refiner <idea>`** — identical to `/refine-requirements`. The prompt
  is a thin wrapper that invokes that same agent with the task context;
  the `.agent.md` file is the single source of truth for the process
  (same for `/create-implementation-plan` vs `@planner`). Two doors, one
  behavior.

In **Copilot CLI** (no prompt-file support): only the third form exists —
drive the agents manually in stage order (refiner → spec-critic → planner →
implementer → pattern-critic → scribe), following each exit HANDOFF block.
Don't assume `/run-pipeline`'s automated subagent routing works there
until you've tested it.

The `### HANDOFF:` blocks are a text convention, not a mechanism: an agent
that emits one has STOPPED. Nothing runs next unless you (manual mode) or
the `/run-pipeline` orchestrator invokes it.

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

## How do I run the `kb:*` scripts without committing the `package.json` entries?

The `npm run kb:*` entries are pure aliases — the scripts have zero npm
dependencies (Node built-ins only), so revert the installer's edit
(`git checkout -- package.json`) and call them directly:

| Instead of | Run |
|---|---|
| `npm run kb:validate` | `node scripts/kb/kb-validate.mjs` |
| `npm run kb:index` | `node scripts/kb/kb-index.mjs` |
| `npm run kb:check` | `node scripts/kb/kb-index.mjs --check` |
| `npm run kb:resolve -- --tags a,b` | `node scripts/kb/kb-resolve.mjs --tags a,b` |
| `npm run kb:drift` | `node scripts/kb/kb-drift.mjs` |
| `npm run kb:guard` | `node scripts/kb/kb-guard.mjs` |
| `npm run kb:catchup` | `node scripts/kb/kb-catchup.mjs` |
| `npm run kb:catchup -- --mark` | `node scripts/kb/kb-catchup.mjs --mark` |

Note the `--` vanishes — it is an npm-ism for passing arguments through;
direct `node` takes them natively. The pre-commit hook already calls
`node scripts/kb/...` directly and never touches `npm run`, so it keeps
working; `kb-drift` finds `typescript` in the repo's existing
`node_modules`, also unaffected.

Alternatives, if typing the paths gets old:

- **Local wrapper** at `scripts/kb/kb` (the directory is already in
  `.git/info/exclude` during a trial, so it stays local for free):

  ```bash
  #!/bin/sh
  # usage: scripts/kb/kb validate|index|check|resolve|drift|guard|catchup [args...]
  cmd="$1"; shift
  [ "$cmd" = "check" ] && exec node scripts/kb/kb-index.mjs --check
  exec node "scripts/kb/kb-$cmd.mjs" "$@"
  ```

  `chmod +x scripts/kb/kb`, then e.g. `scripts/kb/kb catchup --mark`.
- **Shell aliases** in your `~/.zshrc`/`~/.bashrc`
  (e.g. `alias kbv='node scripts/kb/kb-validate.mjs'`) — machine-local,
  repo-independent, but only work from the repo root.
- **Not recommended:** keeping the `package.json` edit uncommitted (one
  `git add .` away from leaking; constant `git status` noise) or
  `git update-index --skip-worktree package.json` (silently skips
  teammates' real `package.json` changes on pull).

One caveat: the installed prompts and docs say `npm run kb:*`, so an agent
following e.g. `/sync-cards` will hit "missing script". Agents usually
recover by falling back to direct `node`, but don't rely on it — add one
line to the repo's `AGENTS.md` (also local-only during a trial):
"`npm run kb:*` aliases are not installed — invoke the scripts directly as
`node scripts/kb/<script>.mjs`." Delete the line when the team adopts the
kit and the `package.json` entries get committed.

## Does any of this send data anywhere?

No. Every `kb:*` script, the hook, and the installer are deterministic,
local-only Node/shell — no network calls, no telemetry. The only things
that cost tokens (and talk to a model) are the chat prompts and agents you
invoke explicitly, through your own Copilot/agent setup.
