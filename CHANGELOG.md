# Changelog

All notable changes to semiPilot. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) (0.x: minor versions may change behaviour, and say how in
[docs/upgrading.md](docs/upgrading.md)). Branches: `v5` = 0.2.x, `v4` = 0.1.x, `v3` = the manual pipeline.

## [0.2.0] — 2026-10-20

### Added
- **Claude Code as a loop harness**, next to GitHub Copilot CLI: `harness: claude | copilot` per project,
  `semipilot init --harness`. Headless calls use `--output-format json`, `--no-session-persistence` and
  `--permission-mode dontAsk`; cost per call is read from the JSON and summed in the report.
- **Harness adapters** (`harness.py`) with per-role **permission profiles** (`read`, `write`, `none`) mapped to each
  CLI's allow/deny rules, and per-harness failure patterns (Claude Code's from its documented error messages).
- **Agent Skills pack** (`skills/`): `semipilot-refine`, `semipilot-spec-critic`, `semipilot-run`,
  `semipilot-scribe`, `semipilot-knowledge` — each with references, examples and a README; installed by `init` into
  `.agents/skills/` (Copilot) and/or `.claude/skills/` (Claude Code).
- **Plugin manifests** (`.claude-plugin/`), read by Claude Code and Copilot CLI, so the skills install as a plugin.
- **Skill pack checks** (`tests/test_skills.py`): every skill is validated against the Agent Skills format.
- **Knowledge layer bundled and ported to Python**: `scripts/kb/kb.py` (validate, index, resolve, drift, guard,
  catchup) — standard library only; `semipilot kb init` installs the layer (templates, hook, CI);
  `semipilot kb <command>` runs it. `drift` reads Python imports as well as TypeScript/JavaScript, without the
  TypeScript package.
- The orchestrator **resolves knowledge tags itself** and puts the reading list into every agent's prompt; unknown
  tags fail preflight before any agent call.
- **Branch guard**: an agent that switches branches halts the run (`guardrail_violation`) and is switched back.
- Project overrides for role definitions: `.semipilot/roles/<role>.md`.
- **A model per role** (`models:`), and the report's cost broken down by role.
- Claude Code `bare` option (`--bare`: less startup context per call; API key only).
- `doctor` checks the harness, the skill pack, the instructions file (AGENTS.md / CLAUDE.md interplay) and lists
  v0.1 leftovers.
- Documentation set: getting started, concepts, harnesses, skills, knowledge layer, configuration, CLI, architecture,
  troubleshooting, upgrading; SECURITY.md and CONTRIBUTING.md; CI on Linux and macOS, Python 3.9 and 3.12.

### Changed
- **No model call for health checks.** Preflight only checks that the agent CLI is installed; the planner's questions
  call is the first real call and catches a login problem before any branch exists. `doctor` makes a model call only
  with `--live` (`--offline` is now the default and still accepted).
- Loop roles are **inlined** into each call instead of loaded with `--agent`; the same prompts run on every harness.
- `AGENTS.md` is the default instructions file; `init` creates it only when no instructions file exists.
- The deny list now also covers `git commit`, `git switch`, `git stash`, `git rebase`, `git merge`.
- Stop reason `copilot_unavailable` → `agent_unavailable`.
- `preflight.token_expiry_env` → `SEMIPILOT_TOKEN_EXPIRES_AT` (the old variable is still read).
- Top-level `failure_patterns` now adds to the active harness's patterns.
- The whole orchestrator test suite runs once per harness against a fake agent CLI that speaks both dialects.

### Removed
- `.github/prompts/*.prompt.md` and `.github/agents/*.agent.md` installation (replaced by the skills).
- Config keys `runner.agents`, `runner.allow_tools`, `runner.deny_tools` (ignored; `doctor` lists them).

### Fixed
- Read-only loop roles were instructed to run the knowledge-layer resolver but had no permission to run it; the
  orchestrator now resolves the tags for them.
- `BLOCKED: <question>` is now acted on: from the planner or test-writer it halts the run (`blocked`) with the
  question; from the implementer it blocks the task with the question and reverts its changes.
- `resume` continues at the stage that stopped (planning, locked tests or tasks) and gives blocked tasks a fresh set
  of attempts; before, a halt during planning or test-writing could not be resumed and blocked tasks never retried.
- A run whose tasks end blocked reports `completed_with_blocked` (exit 2) instead of `completed`.
- An acceptance criterion wrapped over several indented lines keeps its `[check: …]` tag (preflight used to read
  only a criterion's first line and reject it as untagged).
- YAML comments in `requirements.md` frontmatter no longer break approval and branch names.
- The loop's commits and reverts skip git hooks (`--no-verify`), so a project hook cannot crash a run.
- A tree reset never touches another branch: if an agent switched branches, the loop switches back and halts.
- Knowledge tags are validated and shell-quoted before reaching the resolver.
- Automatic resume after `infra.retry_window` no longer counts the sleep against the wall-clock budget.
- Claude Code: failures are classified from `subtype` / `api_error_status`; `error_max_turns` and
  `error_max_budget_usd` are task failures, not outages; patterns never match telemetry numbers in the JSON.
  Settings files are not loaded for loop calls (`--setting-sources ""`) and the state dir is denied to file tools.
- Cost in the report includes the preflight calls.
- `kb drift` ignores imports in comments and template literals; `kb init` writes one CI workflow per monorepo
  project and warns instead of replacing another hook manager's `core.hooksPath`.
- `init` never downgrades newer skills and never overwrites `.semipilot/config.yaml` or `.semipilot/.gitignore`.
- `runner.command` paths with backslashes work on Windows.

## [0.1.0] — 2026-09-28 (branch `v4`)

### Added
- The `semipilot` CLI: requirements → Gate 1 → PilotInLoop on GitHub Copilot CLI, installable with pipx or from a
  download; subfolder projects (`init --here`); configurable branch and commit names; knowledge-layer aware.
