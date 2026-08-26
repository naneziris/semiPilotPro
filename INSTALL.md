# INSTALL — adopting the kit in a repository

Two phases: a **mechanical install** (minutes, `install.sh`) and a
**knowledge bootstrap** (½–2 days, AI-drafted + human-approved). Do not skip
the human gates in phase 2 — an unreviewed knowledge layer is deterministic
misinformation.

## Phase 0 — Decide scope (5 minutes, honest answers required)

1. **Who owns maintenance?** If nobody will keep cards current, install ONLY
   the instruction router (copy `templates/copilot-instructions.template.md`
   in by hand, fill it, stop). A full layer without an owner rots.
2. **Knowledge layer only, or + pipeline?** The layer alone already makes
   Copilot materially better. Add `--with-pipeline` when you want the full
   refine → gates → implement → scribe process.
3. **Language check.** TS/JS repos get the full suite. Other stacks: the
   drift check needs an import extractor for your language (or disable that
   one CI job) — everything else is language-agnostic markdown + JSON.

## Phase 1 — Mechanical install

```bash
./install.sh /path/to/repo <system-name> [--with-pipeline]
cd /path/to/repo
git config core.hooksPath .githooks        # once per clone, every teammate
```

What it did: copied `scripts/kb/` (+ `kb.config.json` defaults), the
pre-commit hook, the CI workflow, VS Code setting, the knowledge prompts,
the bootstrap prompt + cartographer agent, and the `{{TODO}}`-marked
templates into their real locations (`.github/copilot-instructions.md`,
`docs/cards/_vocabulary.md`, `docs/README.md`, `docs/decisions.md`,
`docs/dependencies.md`, `docs/CHANGELOG.md`). With `--with-pipeline`, also
the 6 agents, 9 pipeline prompts, code-analyzer skill, `semipilot-core.md`,
and `INSTRUCTIONS.md`. It never overwrites: existing files are skipped and
reported (it prints merge notes for `AGENTS.md` / `.vscode/settings.json`).

Post-install checks:
- `scripts/kb/kb.config.json` — set `srcDirs`/`aliases`/`extensions` to your
  layout (defaults: `src/`, `@/ → src/`, `.ts/.tsx`).
- No `package.json`? The `npm run kb:*` aliases in the hook, CI workflow,
  and prompts must become direct `node scripts/kb/<script>.mjs` calls.
- Monorepo? Install per package OR at the root with cards claiming
  `packages/<name>/…` paths — root install is simpler and usually right.

## Phase 2 — Knowledge bootstrap (the real work)

Open the repo in VS Code and run **`/bootstrap-knowledge-layer`** in Copilot
chat. It walks these steps, stopping for your approval at each gate:

1. **Inventory** — stack, commands, module boundaries, contracts, seams.
2. **Vocabulary** (GATE) — 20–50 tags drafted in your team's language; you
   edit and approve. This list is human-owned; everything downstream
   inherits its quality.
3. **Instruction router** (GATE) — fills `copilot-instructions.md` (≤ 80
   lines: commands, evidence-based invariants, cross-cutting triggers) and
   3–6 path-scoped area instruction files (≤ 40 lines each).
4. **Cards, seam-first** (GATE per batch) — card list approved first, then
   ~5 cards per review batch, contracts-touching modules first. Large repo?
   The bootstrap can fan out to `@cartographer` per domain.
5. **Go green** — `kb:validate`, `kb:index`, `kb:drift` (declare the real
   edges it finds), spot-check `kb:resolve` output; seed ADRs and the
   dependency policy from evidence.
6. **Handover** — remaining TODOs, smoke test (ask Copilot cold a question
   an invariant answers), commit.

Then commit everything. From here on, retrieval goes through `kb:resolve`
only, and card updates ride in the same PR as code changes.

## Phase 3 — Daily use

- The installed `docs/README.md` is the layer's manual (workflows,
  commands, troubleshooting).
- With the pipeline: `INSTRUCTIONS.md` is the manual for the full
  refine → gates → implement → scribe flow; `semipilot-core.md` is the
  contract. Trivial edits skip the pipeline — the hook still guards them.
- CI: `validate` + manifest check block from day one; `drift` is
  warning-only (`continue-on-error`) — remove that line once it has been
  quiet for a while; `guard` never blocks, it nags in the step summary.

## Using Copilot CLI instead of VS Code chat

Everything works in Copilot CLI except prompt files — the CLI does not (yet)
pick up `.github/prompts/*.prompt.md` as slash commands:

- **Works as-is:** `.github/agents/*.agent.md` (invoke via `/agent`, by
  name, or `copilot --agent <name>`), `.github/copilot-instructions.md`,
  `AGENTS.md` (no VS Code setting needed), path-scoped
  `.github/instructions/*.instructions.md`, `.github/skills/code-analyzer`,
  and all `kb:*` scripts / the hook / CI (editor-agnostic).
- **Prompt-file gap, bridged by the router:** the installed `AGENTS.md`
  block tells the agent to read and execute the matching
  `.github/prompts/*.prompt.md` when you ask for a workflow in natural
  language ("sync the cards", "run the pipeline"). You can always be
  explicit: "Read `.github/prompts/sync-cards.prompt.md` and follow it."
- **Verify on first use:** whether the CLI honors agent `model:` pins (the
  Sonnet-critic / Opus-gate split — check with `/model`), and whether the
  `/run-pipeline` orchestrator's subagent handoffs work in the CLI's agent
  runtime. If they don't, run the pipeline steps manually via the documented
  partial entry points.

## Solo / POC mode (adopting before the team is on board)

Running the layer alone for a sprint while teammates commit without touching
cards is a supported mode:

- **Skip the CI workflow at first** (delete or don't commit
  `.github/workflows/knowledge-layer.yml`): its blocking validate job would
  fail teammates' PRs the moment they rename a card-claimed file — the wrong
  first impression for a POC. The pre-commit hook is per-clone
  (`core.hooksPath`), so it enforces only on YOUR machine.
- **Catch up after every pull with `npm run kb:catchup`**: it keeps a
  personal baseline in `.git/` (never committed) and lists exactly which
  cards teammates' changes touched without a card update — zero tokens.
  Fix the flagged cards (by hand for free, or `/sync-cards` scoped to the
  printed file list for a small token cost), `kb:index`, then
  `kb:catchup -- --mark`.
- When the team adopts: commit the CI workflow, everyone runs the one-line
  hook config, and `kb:catchup` becomes unnecessary (the same-PR discipline
  replaces it).

## Known limitations (candidly)

- `kb-drift` is TS/JS-only as shipped (uses the repo's `typescript`
  package). Swapping in another language means replacing two functions in
  `kb-drift.mjs` (`importSpecifiers`, `resolveSpecifier`).
- The pipeline files assume GitHub Copilot (VS Code chat, or the CLI — see
  "Using Copilot CLI" above; the CLI lacks `.prompt.md` support, bridged via
  the `AGENTS.md` router). Claude Code and other agents still benefit —
  `AGENTS.md` routes them to the same knowledge layer and playbooks — but
  `.agent.md`/`.prompt.md` mechanics are Copilot's.
- Agent `model:` pins (Sonnet 4.6 / Opus 4.8) carry over from the team
  standard; GHCP may ignore the field — name the model when invoking a
  critic if it matters.
- The two human gates and the card-review batches are not optional
  ceremony. Every shortcut here converts directly into confidently wrong
  retrieval later.

## Updating a repo when the kit evolves

The scripts are the only truly shared code. To upgrade: re-copy
`core/scripts/kb/*.mjs` (they carry no repo state — config lives in
`kb.config.json`, knowledge in the cards) and diff
`core/githooks`/`core/workflows` by hand. Templates and pipeline files are
forked at install time by design — repos customize them; do not blind-copy
over them.
