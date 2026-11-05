# Configuration

semiPilot reads its built-in defaults (`src/semipilot/defaults.yaml`) and deep-merges your
`.semipilot/config.yaml` over them. Maps merge key by key; **lists replace** the default list. `semipilot config`
prints the effective result.

`semipilot init` writes a short file with only what most projects touch:

```yaml
harness: claude

checks:
  - name: lint
    cmd: ruff check .
  - name: tests
    cmd: python -m pytest -q {task_tests}

tests:
  patterns:
    - tests/**/*.py
```

## Keys

### `harness`
`copilot` (GitHub Copilot CLI) or `claude` (Claude Code). The agent CLI that runs every loop call. Aliases
`copilot-cli`, `claude-code` are accepted. See [harnesses.md](harnesses.md).

### `checks`
The definition of done: a list of `{name, cmd}` run in order after every implementer attempt, stopping at the first
failure, and once more (without `{task_tests}`) as the final full suite. `{task_tests}` expands to the current
task's locked test files plus the files of tasks already done. A `cmd` starting with `#` is a TODO and blocks the run.
`check_output_tail_lines` (200) and `check_output_max_bytes` (16000) cap how much failing output goes back to the agent (the end is kept, colour codes are stripped, very long lines are cut). Quiet reporters (no colour, no coverage table) make the most of it.

### `tests`
| Key | Default | |
|---|---|---|
| `patterns` | Python, TS/JS, Go globs | files the test-writer may create and that get locked |
| `contract_error_patterns` | import/name/signature errors (Python, TS, Go) | failures that trigger the one test-fixer pass |

### `runner`
| Key | Default | |
|---|---|---|
| `command` | `null` | override the executable, e.g. `/opt/bin/claude` (null = the harness default) |
| `model` | `null` | pin a model for every loop call (`--model`) |
| `call_timeout_seconds` | `1200` | per call; a timeout is a task failure and resets the tree |
| `forbidden_flags` | `[]` | extra flags to refuse (session and permission-bypass flags are always refused) |
| `extra_flags` | `[]` | appended to every call |

### `models`
A model per loop role (`planner`, `plan-fidelity-critic`, `plan-critic`, `test-writer`, `test-fixer`, `implementer`); `null`
falls back to `runner.model`, and that to the CLI's default. Typical use: keep the strongest model on planner and
critics, try a cheaper one on the implementer, compare the report's cost by role and its retries before and after.

### `roles`
The permission profile for each loop role: `read`, `write` or `none`. Defaults: planner/plan-fidelity-critic/plan-critic
`read`, test-writer/test-fixer/implementer `write`, health (`doctor --live`) `none`.

### `private` and `git.local_paths` — keep files out of git

For trialling semipilot in a team repository before proposing it (`semipilot init --private` sets both up):

```yaml
private: true            # semipilot's own files are never committed
git:
  local_paths:           # your uncommitted changes that must stay uncommitted
    - ".github/"         # a folder (trailing /)
    - "package.json"     # a file — see the caveat below
```

| | `private: true` | `git.local_paths` |
|---|---|---|
| What | `.semipilot/`, the skill pack, `scripts/kb/`, `.githooks/`, `docs/cards/`, the knowledge-layer workflow, and `AGENTS.md` / `CLAUDE.md` / the `docs/*.md` skeletons when git does not track them | whatever you list: files, folders ending in `/`, globs, relative to the project |
| Committed | never — listed in `.git/info/exclude`, so `git status` does not show them | never — left out of every commit |
| Clean-tree check | ignored | ignored (plain `git status` still shows modified tracked files: that is git, not semipilot) |
| Resets after a failed attempt | kept | kept |
| Agents | read them as usual | read them; may not create, change or delete them — a plan needing one is rejected, an edit is reverted |

The result: the run branch contains only the feature's code commits, so the PR shows nothing of the workflow.
Specs, answers, decisions, the report and the checkpoint stay as local files next to it.

**Caveat — local files the feature needs.** A file in `local_paths` cannot be part of the feature. If a feature
needs it (a new dependency in `package.json`, a CI change under `.github/`), the planner answers `BLOCKED:` and you
decide: commit your local change first, or take the path out of `local_paths` for that run. So keep workflow-only
scripts out of `package.json`: the `checks` can call the tools directly (`npx vitest run {task_tests}`,
`npx tsc --noEmit`).

**Ending the trial.** Set `private: false` and empty `local_paths`; the next command removes semipilot's block from
`.git/info/exclude`, and you commit what the team adopts. Files committed *before* you turned private mode on stay
tracked — `doctor` lists them; `git rm --cached -r <path>` stops tracking them.

### `harnesses.<name>`
Everything harness-specific. `semipilot config` shows the full defaults.

| Key | | |
|---|---|---|
| `command` | both | the executable |
| `allow.read` / `allow.write` / `allow.none` | both | tool rules per profile, in the harness's own syntax |
| `deny` | both | rules denied on every call (they win over allow) |
| `failure_patterns.fatal` / `.quota_exhausted` / `.transient` | both | regexes classifying a failed call |
| `extra_flags` | both | appended to every call for this harness |
| `prompt_file_threshold` | copilot | default 98304 bytes; a longer prompt is written to a file the agent reads instead of going onto the command line (OS argument limits) |
| `permission_mode.<profile>` | claude | default `dontAsk`; `bypassPermissions` is refused |
| `max_turns.<profile>` | claude | `--max-turns` per profile (empty = CLI default) |
| `max_budget_usd_per_call` | claude | `--max-budget-usd` on every call |
| `bare` | claude | default `false`; `true` passes `--bare` — less startup context per call, but needs `ANTHROPIC_API_KEY` (no subscription login) |
| `setting_sources` | claude | default `""`: `--setting-sources ""` loads no user/project/local settings file, so an `allow` rule there cannot widen a profile; `null` = Claude Code's default |

### `failure_patterns`
Extra regexes for the active harness, added to its own list:

```yaml
failure_patterns:
  transient: ["upstream connect error"]
```

### `budget`
| Key | Default | |
|---|---|---|
| `max_retries_per_task` | 3 | implementer attempts per task |
| `max_iterations` | 30 | implementer calls per run |
| `wall_clock_seconds` | 21600 | 6 h |
| `max_critique_rounds` | 2 | rejected plan rounds before `plan_rejected` |
| `max_contract_fixes_per_task` | 1 | test-fixer passes per task |

### `guardrails`
| Key | Default | |
|---|---|---|
| `max_expected_files_per_task` | 5 | plan validation |
| `scope_tolerance_extra_files` | 2 | files outside the task tolerated (logged) |
| `diff_cap_lines_per_task` | 400 | above → task blocked |
| `diff_cap_lines_per_run` | 3000 | above → run stops |
| `allow_new_test_files` | true | implementer may add (never modify locked) tests |
| `stuck_detection` | true | same error signature twice → blocked |

### `infra`
| Key | Default | |
|---|---|---|
| `backoff_start_seconds` / `backoff_cap_seconds` | 60 / 900 | exponential backoff with ±20 % jitter |
| `max_outage_seconds` | 5400 | continuous outage before the breaker trips |
| `max_total_outage_seconds` | 9000 | total outage per run |
| `unknown_as_transient_once` | true | an unclassified failure is retried once |
| `retry_window` | null | `"HH:MM"`: after a breaker trip before that time, sleep and resume once |

### `knowledge_layer`
| Key | Default | |
|---|---|---|
| `mode` | `auto` | `auto` (use when present), `on`, `off` |
| `validate_cmd` | `auto` | `kb.py validate`, or the Node script for older installs |
| `resolve_cmd` | `auto` | must contain `{tags}` |

### `instructions_file`
`auto`: `AGENTS.md`, else `.github/copilot-instructions.md`, else `CLAUDE.md`. Named in every loop prompt and checked
by `doctor` and the plan critic.

### `preflight`
| Key | Default | |
|---|---|---|
| `health_prompt` | "Reply with exactly the word OK…" | the one call `doctor --live` makes (preflight makes none) |
| `auth_check_cmd` | null | e.g. `gh auth status` |
| `token_expiry_env` | `SEMIPILOT_TOKEN_EXPIRES_AT` | ISO timestamp; preflight refuses when it expires before the wall-clock budget ends (`COPILOT_TOKEN_EXPIRES_AT` still read) |
| `criterion_tag_regex` | `\[check:\s*(?P<ref>[^\]]+)\]` | the acceptance-criterion tag |

### `git`
| Key | Default | Placeholders |
|---|---|---|
| `branch` | `{type}/{feature}` | `{type}` (from the spec's `type:`, default `feat`), `{feature}`, `{date}` |
| `commit` | `{type}({feature}): {subject}` | `{type}`, `{feature}`, `{subject}` |

### `state_dir`
`~/.semipilot/state` — where `plan.json` lives during a run, outside the repository so the implementer is never
pointed at it. On Claude Code the adapter also denies `Read`/`Edit` on this folder.

## Prompt and role overrides

- `.semipilot/roles/<role>.md` replaces a role definition (`planner`, `plan-fidelity-critic`, `plan-critic`).
- `.semipilot/prompts/<name>.md` replaces a task prompt (`planner-questions`, `planner-plan`,
  `plan-fidelity-critic`, `plan-critic`, `test-writer`, `implementer`, `test-fixer`).

Before 0.2.1 the plan-fidelity critic was called `spec-critic`; config keys and override files under that name
still work, and `doctor` asks you to rename them.

Start from the packaged files in `src/semipilot/roles/` and `src/semipilot/prompts/`; keep their `{placeholders}`
and their output formats — the orchestrator parses them. These files are Python format strings: write a literal brace
as `{{` / `}}` (as the JSON examples in them do), or the call fails.

## Keys from v0.1 that no longer apply

`runner.agents` (roles are inlined), `runner.allow_tools` / `runner.deny_tools` (now `harnesses.<name>.allow` /
`deny`). `semipilot doctor` lists any it finds.
