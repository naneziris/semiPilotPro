# Changelog

All notable changes to semiPilot. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) (0.x: minor versions may change behaviour, and say how in
[docs/upgrading.md](docs/upgrading.md)). Branches: `v6` = 0.3.x, `v5` = 0.2.x, `v4` = 0.1.x, `v3` = the manual pipeline.

## [0.3.0] — 2026-11-12

Where the human is. 0.2 had one level of autonomy for every feature and handed over a whole branch to review at
the end. 0.3 makes autonomy a property of the feature, prepares the review, measures what a run costs, and adds a
second, much smaller loop for work that can be verified without a person. Background:
[docs/design/v6-loops-and-factories.md](docs/design/v6-loops-and-factories.md).

### Added
- **Risk tiers** — `risk: low | medium | high` in the requirements' frontmatter (`semipilot-refine` proposes it,
  Gate 1 checks it). `medium` stops the run once after the critics accept the plan (`plan_approval`); `high` also
  stops after every finished task (`task_review`). The plan's paths raise the tier (`autonomy.escalate`; by default
  auth, billing, payments, migrations, SQL and CI workflows mean at least `medium`) and never lower it.
  `autonomy.tiers` sets what each tier adds; `autonomy.require_risk` refuses requirements without a tier.
- **`semipilot approve [feature]`** — records your approval of the plan (with the plan's hash; a changed plan needs
  approval again) and continues. **`semipilot replan <feature> -m "<text>"`** — sends the plan back with your words,
  which the planner gets above the critics'; the new plan stops for approval again.
- **Red check** — right after the tests are locked, each task's tests run with no implementation and must fail. A
  task whose tests already pass is flagged in the report (`tests.red_check: warn | halt | off`). The same step flags
  an acceptance ref that no locked test names.
- **Reviewer agent** — one read-only call after the last task grades the diff against a rubric (spec fidelity, test
  honesty, boundaries, simplicity, failure handling, security and data, readability, assumptions), lists findings
  by severity and names what to read first. Advice, never a gate: it cannot edit, cannot fail a run, and a blocker
  or failed rubric item forces its verdict to *needs changes*. Override the rubric with
  `.semipilot/roles/reviewer.md`; `semipilot review <feature> --agent` runs it again; `review.agent: false` turns
  it off.
- **Review packet** — `report.md` opens with section 0: risk tier, reviewer verdict, *needs attention*, *read
  first*, evidence per acceptance criterion (criterion → test file → task → commit → red first?), where the change
  is (files by size, each with the task that planned it), and a reading order commit by commit.
- **Usage and cost on both harnesses** — calls and minutes per role always; dollars and tokens on Claude Code;
  premium requests and tokens on Copilot CLI, read from the `session.shutdown` event in its session files (or, with
  `harnesses.copilot.usage.silent: false`, from the stats block it prints). `cost.premium_request_usd` turns
  requests into dollars. Totals in `implementation-progress.json` (`budget.usage`), one line per call in
  `.semipilot/runs/<run-id>/calls.jsonl`.
- **Spend caps** — `budget.max_cost_usd`, `budget.max_premium_requests`: the run stops between tasks.
- **`semipilot chore [name]`** — one small unattended fix per run (`chores.items`: a `find` command and/or an
  `instruction`). Kept only if: the checks pass on the base and after the fix, no existing test or instructions file
  changed, the change is within `max_files` / `max_diff_lines`, and the finding is gone with fewer findings than
  before. Remembers failures, never fixes a finding twice while its branch waits for review, and stops at
  `max_open` unmerged chore branches. `--list`, `--dry-run`, `--history`, `--reset`.
- **`semipilot intake <issue>`** — reads a GitHub or GitLab issue (`gh` / `glab`) into
  `.semipilot/features/<slug>/issue.md`; `/semipilot-refine <slug>` uses it as the idea and treats its text as
  data, not instructions.
- **`semipilot mr [feature]`** (alias `pr`) — pushes the run branch and opens a draft request into the branch the
  run started from, with a description built from the review packet and `Closes #n` when the feature came from an
  issue. `forge.open_mr: auto` does it after a completed run; `chores.open_mr: true` for chores. `--dry-run`.
- `status` shows *waiting for you* stages and the reviewer's verdict; `doctor` shows risk-tier settings, the forge
  it detected and where Copilot usage is read from.
- Docs: [autonomy.md](docs/autonomy.md), [chores.md](docs/chores.md), [forge.md](docs/forge.md).

### Changed
- Exit code **3** now also means a risk tier's gate (`plan_approval`, `task_review`), not only unanswered questions.
- The loop makes one more call per run (the reviewer) and one scoped test run per task before implementing.
- Skills 0.3.0: `semipilot-refine` proposes a risk tier and accepts an `issue.md` as the idea;
  `semipilot-spec-critic` checks the tier (checklist item 8) and states it in its APPROVED block; `semipilot-run`
  walks through plan approval, task review and the review packet, and may run `semipilot mr` when asked.
- `resume` clears the previous stop detail; a checkpoint written by a newer semipilot no longer crashes an older
  field set on load.
- Agents still cannot push. `semipilot mr` (and the two `open_mr` settings) are the only paths by which a branch
  leaves the machine, and the program pushes, not an agent.

### Not verified against the real services
- The Copilot usage readers (session files, stats block) follow the formats documented in the CLI's issue tracker;
  they are tested against a fake CLI only. `doctor` says which source it will use; the report says when nothing was
  reported.
- `intake` and `mr` are tested against a fake `gh`/`glab` and a local bare remote. Use `semipilot mr --dry-run`
  first; `forge.commands` replaces a command line that your CLI version does not accept.

### Deliberately not added
- **Parallel runs / worktrees.** The bottleneck is a person reading the result; running more loops deepens the
  pile in front of them. One reviewed feature at a time.
- **Production signals feeding the queue.** Out of scope until the loop itself has proven its worth.
- **Cross-harness critics** (plan on one CLI, critique on the other). Left for later by decision.


## [0.2.2] — 2026-11-04

Fixes from the first real runs with the Copilot harness, and less guessing about what to run where.

### Added
- **`private: true`** (`semipilot init --private`) — trial semipilot in a team repository without the team seeing
  it. semipilot's own files (`.semipilot/`, the skill pack, the knowledge-layer tooling, an untracked `AGENTS.md` /
  `CLAUDE.md`) are listed in `.git/info/exclude` (git's local-only ignore list) and never committed: no
  auto-commit of the spec onto the base branch, no run-state commits. A run branch holds only the feature's code
  commits, so its PR is clean. Checkpoints and reports stay as local files; `resume` uses them.
- **`git.local_paths`** — your own uncommitted changes that must stay uncommitted (files, folders ending in `/`,
  globs; `init --private` adds `.github/`). The clean-tree check ignores them, no commit includes them, every reset
  keeps them, and agents may not change them: a plan whose `expected_files` include one is rejected, an edit to one
  is reverted and the attempt retried (blocked after a second time), and the prompts list them with "answer
  `BLOCKED:` if the feature needs one changed".
- `doctor` shows the local set, the uncommitted local changes, and semipilot files committed before private mode.

### Fixed
- **"argument list too long" with the Copilot harness.** The prompt went onto the command line (`copilot -p
  <prompt>`); large prompts exceeded the OS limit and the CLI never started. Prompts above
  `harnesses.copilot.prompt_file_threshold` (96 KiB) now go to a file in the run folder that the agent is told to
  read (it is given the `read` tool for that). A CLI that cannot be started at all now stops the run cleanly with
  `agent_start_failed` and a saved checkpoint, instead of a traceback.
- **Failing check output is capped by size**, not only by lines: `check_output_max_bytes` (16 000), colour codes
  stripped, lines over 2 000 characters cut, the end kept.
- **`resume` said "nothing to resume" from the base branch.** The checkpoint is committed on the run branch;
  `resume` now finds it on any local branch and switches there itself.
- **`run` after an interruption said "branch already exists".** It now recognises an earlier run of the feature
  and says `semipilot resume <feature>` (or how to start over), before any other check — and no longer
  auto-commits that run's state onto the base branch.
- **"not approved"** now names the branch it checked and, when the spec is approved on another local branch, says
  which one.

### Changed
- Every stop prints `Stopped: <what happened>  [reason]`, the last line of the detail, the report path, and
  `Next: <command>`.
- `run` / `resume` print a note when they look started from inside an agent session (no TTY, or Claude Code's
  `CLAUDECODE`): run them in a plain terminal tab.
- `semipilot-run` skill: the agent never starts `run`/`resume` (no detached or "separate" terminals; foreground only
  when the user insists), always says `resume` after an interruption, and never checks connectivity or logins
  itself. README and getting-started gain a "where each step happens" table; troubleshooting covers the new
  messages.

## [0.2.1] — 2026-10-21

### Changed
- The loop's `spec-critic` role is now **`plan-fidelity-critic`**. It always reviewed the *plan* against the approved
  requirements, never the requirements themselves (that is Gate 1, the `semipilot-spec-critic` skill), and the
  shared name made the two look like one check run twice. Renamed in prompts, logs, the report's cost by role,
  `models:` and `roles:`. The old config keys and `.semipilot/{roles,prompts}/spec-critic.md` overrides still
  work; `doctor` asks you to rename them. Gates in the loop are now numbered 2a (fidelity) and 2b (plan).
- Skills and plugin manifests carry version 0.2.1 (one version for the whole package; skill content unchanged).

### Fixed
- An acceptance criterion wrapped over several indented lines keeps its `[check: …]` tag (preflight used to read
  only a criterion's first line and reject it as untagged).

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
