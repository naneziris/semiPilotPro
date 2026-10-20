# Upgrading from v4 (semipilot 0.1) to v5 (0.2)

0.2 makes semiPilot harness-neutral: the loop runs on GitHub Copilot CLI **or** Claude Code, the interactive steps
are Agent Skills instead of Copilot prompt files and agents, and the knowledge layer's tooling is one Python file.
Your requirements, plans, reports and cards carry over unchanged.

## Steps

```bash
pipx install --force git+https://github.com/naneziris/semiPilotPro.git@v5     # or download the v5 ZIP
cd your-repo
semipilot init --harness copilot      # keeps your config (only adds `harness:`), installs the skill pack (or claude)
semipilot kb init --force             # only if you have the knowledge layer: adds kb.py, switches hook + CI
semipilot doctor
```

Then clean up what `doctor` lists as no longer used (it never deletes anything itself):

| v4 file | Replaced by |
|---|---|
| `.github/prompts/refine-requirements.prompt.md`, `.github/agents/refiner.agent.md` | `semipilot-refine` skill (`/semipilot-refine`) |
| `.github/prompts/spec-critic.prompt.md`, `.github/agents/spec-critic.agent.md` | `semipilot-spec-critic` skill |
| `.github/agents/pilotinloop-{planner,spec-critic,plan-critic}.agent.md` | inlined role prompts (`src/semipilot/roles/`) |
| `scripts/kb/kb-*.mjs`, `kb:*` scripts in `package.json` | `scripts/kb/kb.py` |

Commit the result. Progress files are unchanged, so a run interrupted on v4 can be resumed with v5.

**Customised the v4 loop agents?** If you edited `.github/agents/pilotinloop-*.agent.md`, those edits no longer take
effect. Port them to `.semipilot/roles/<planner|spec-critic|plan-critic>.md` (start from `src/semipilot/roles/`).

**`runner.command` set in your config?** It overrides the harness's executable. Remove it when you switch harness (or
use `harnesses.<name>.command`); `init` warns when it does not match.

## What changed

**The loop no longer uses `--agent`.** The planner and critic definitions are inlined into every call, followed by
the task. Tool restrictions moved to permission profiles mapped to each harness's own rules (`read` for planner and
critics, `write` for test-writer, test-fixer and implementer). The orchestrator now also resolves the knowledge
layer's tags itself and hands every agent the reading list — in v4 the read-only roles were told to run `kb-resolve`
but were not allowed shell access to do it.

**Config.** New: `harness`, `roles`, `harnesses.<name>.{allow, deny, failure_patterns, …}`, `instructions_file`.
Gone: `runner.agents`, `runner.allow_tools`, `runner.deny_tools` (ignored; `doctor` lists them). The deny list grew:
`git commit`, `git switch`, `git stash`, `git rebase`, `git merge` are now denied too. `failure_patterns` at the top
level now means *extra* patterns for the active harness. `preflight.token_expiry_env` defaults to
`SEMIPILOT_TOKEN_EXPIRES_AT` (the old `COPILOT_TOKEN_EXPIRES_AT` is still read).

**Stop reason** `copilot_unavailable` is now `agent_unavailable`.

**Instructions.** `AGENTS.md` is the default instructions file (both harnesses read it). An existing
`.github/copilot-instructions.md` keeps working; with Claude Code, `init` adds a one-line `CLAUDE.md` importing it.

**Interactive steps.** `/refine-requirements` → `/semipilot-refine`, `/spec-critic` → `/semipilot-spec-critic`,
`@scribe` → `/semipilot-scribe`. New: `/semipilot-run` (operate the loop from chat) and `/semipilot-knowledge`
(the knowledge-layer workflows that used to be `/bootstrap-knowledge-layer`, `/impact`, `/new-card`, `/sync-cards`).
VS Code's newer Copilot agent harness does not load `.prompt.md` files; skills work everywhere.

**Knowledge layer.** `kb.py` has the same semantics and produces the same content as the Node scripts on the same
cards (the same resolved file lists, the same manifest apart from its `$generated` line). Differences: the output
labels read `kb validate:` / `# kb resolve` / `kb index:` instead of `kb-validate:` / `# kb-resolve` / `kb-index:`
(adjust anything that greps them); `kb.py index --check` accepts a Node-written manifest, but the Node check rejects a
Python-written one — switch the whole team at once; `code:` paths that escape the project root are now rejected; CRLF
card files are accepted. `drift` no longer needs the TypeScript package and also reads Python imports. The CI workflow
needs no install step.

**Safety.** New guard: an agent that switches branches halts the run. Permission-bypass flags are refused for both
harnesses.

See [CHANGELOG.md](../CHANGELOG.md) for the full list.
