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
`check_output_tail_lines` (200) is how much failing output goes back to the agent.

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

### `roles`
The permission profile for each loop role: `read`, `write` or `none`. Defaults: planner/spec-critic/plan-critic
`read`, test-writer/test-fixer/implementer `write`, health `none`.

### `harnesses.<name>`
Everything harness-specific. `semipilot config` shows the full defaults.

| Key | | |
|---|---|---|
| `command` | both | the executable |
| `allow.read` / `allow.write` / `allow.none` | both | tool rules per profile, in the harness's own syntax |
| `deny` | both | rules denied on every call (they win over allow) |
| `failure_patterns.fatal` / `.quota_exhausted` / `.transient` | both | regexes classifying a failed call |
| `extra_flags` | both | appended to every call for this harness |
| `permission_mode.<profile>` | claude | default `dontAsk`; `bypassPermissions` is refused |
| `max_turns.<profile>` | claude | `--max-turns` per profile (empty = CLI default) |
| `max_budget_usd_per_call` | claude | `--max-budget-usd` on every call |
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
| `health_prompt` | "Reply with exactly the word OK…" | the doctor/preflight call |
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

- `.semipilot/roles/<role>.md` replaces a role definition (`planner`, `spec-critic`, `plan-critic`).
- `.semipilot/prompts/<name>.md` replaces a task prompt (`planner-questions`, `planner-plan`, `spec-critic`,
  `plan-critic`, `test-writer`, `implementer`, `test-fixer`).

Start from the packaged files in `src/semipilot/roles/` and `src/semipilot/prompts/`; keep their `{placeholders}`
and their output formats — the orchestrator parses them. These files are Python format strings: write a literal brace
as `{{` / `}}` (as the JSON examples in them do), or the call fails.

## Keys from v0.1 that no longer apply

`runner.agents` (roles are inlined), `runner.allow_tools` / `runner.deny_tools` (now `harnesses.<name>.allow` /
`deny`). `semipilot doctor` lists any it finds.
