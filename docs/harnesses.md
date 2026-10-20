# Harnesses: GitHub Copilot CLI and Claude Code

semiPilot has two halves, and they use agents differently:

| Half | Agent use | Supported |
|---|---|---|
| **Interactive** (refine, Gate 1, run/review help, scribe, knowledge) | Skills in a chat | VS Code Copilot chat, Copilot CLI, Claude Code — any mix, per person |
| **Unattended loop** (plan → critics → tests → implement) | One headless process per call | Copilot CLI **or** Claude Code — one per project (`harness:`) |

A team can chat in different tools and still share one loop runtime. Pick the loop harness per project:

```bash
semipilot init --harness copilot     # or claude — writes `harness:` into .semipilot/config.yaml
```

## Side by side

| | GitHub Copilot CLI | Claude Code |
|---|---|---|
| Login | `copilot login` (or `COPILOT_GITHUB_TOKEN` / `GH_TOKEN`) | `claude`, then `/login` (subscription) or `ANTHROPIC_API_KEY` |
| Headless call | `copilot -p <prompt> -s --no-ask-user` | `claude -p --output-format json --no-session-persistence --permission-mode dontAsk` (prompt on stdin) |
| Permission rules | `--allow-tool=…` / `--deny-tool=…` (deny wins) | `--allowedTools …` / `--disallowedTools …` (deny is evaluated first) |
| Unapproved tool | only allowed tools run; `--no-ask-user` means it never waits for a person | denied, never prompted (`dontAsk`) |
| Answer | stdout | `result` in the JSON object |
| Cost visibility | premium requests (not reported per call) | `total_cost_usd` per call — summed in the report |
| Skills folder (project) | `.agents/skills/` (also reads `.github/skills/`, `.claude/skills/`) | `.claude/skills/` |
| Instructions it reads | `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, `CLAUDE.md` | `CLAUDE.md`, or `AGENTS.md` when there is no `CLAUDE.md` |
| Model pin | `models.<role>`, else `runner.model` → `--model` | `models.<role>`, else `runner.model` → `--model` |

## Permissions

Each loop role runs under a **permission profile** (`roles:` in the config). The defaults:

| Profile | Roles | Copilot CLI | Claude Code |
|---|---|---|---|
| `read` | planner, spec-critic, plan-critic | `read`, `shell(git log/show/diff/status/ls-files)` | `Read`, `Grep`, `Glob`, `Bash(git log/show/diff/ls-files *)`, `Bash(git status)` |
| `write` | test-writer, test-fixer, implementer | `read`, `write`, `shell` | `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `TodoWrite`, `Bash` |
| `none` | `doctor --live` login check | — | — |

On Claude Code the adapter also passes `--setting-sources ""` (no settings file can add allow rules) and denies
`Read`/`Edit` on the state dir. Note that Claude Code's `Read` is not confined to the project by itself; Copilot CLI's
path verification is.

The **deny list** applies to every call and wins over every allow rule: `git push`, `git commit`, `git reset`,
`git clean`, `git checkout`, `git switch`, `git branch`, `git stash`, `git rebase`, `git merge`, `rm`, `sudo`,
`npm publish`, `pip install`, `npm install`, `docker`, `kubectl`, `terraform`, `curl`, `wget`, and web access
(Copilot `url`/`memory`, Claude `WebFetch`/`WebSearch`). The orchestrator owns git; agents never need these.

Flags that would undo the rules are refused when the command line is built: `--allow-all-tools`, `--allow-all`,
`--yolo`, `--allow-all-paths` (Copilot), `--dangerously-skip-permissions` and `permission_mode: bypassPermissions`
(Claude Code) — as are all session flags (`--resume`, `--continue`, `--session-id`, `-r`, `-c`, `--fork-session`).

Override per harness in `.semipilot/config.yaml`, e.g. let read-only roles run your test discovery command:

```yaml
harnesses:
  claude:
    allow:
      read: ["Read", "Grep", "Glob", "Bash(git log *)", "Bash(pytest --collect-only *)"]
```

Lists replace the default list (they are not merged), so copy the defaults from `semipilot config` and edit.

## What has been verified

| Check | Copilot CLI | Claude Code |
|---|---|---|
| Every flag the adapter emits exists | per GitHub's CLI reference (Sept–Oct 2026) | on Claude Code 2.1.304: in `claude --help`, except the optional `--max-turns`, which is accepted but not listed |
| Health call returns the answer | design-time (v0.1 findings) | real call: `result` = `OK`, `is_error` false, cost reported |
| Write profile can edit, deny list blocks `git push` | not yet exercised in a real run | real call: file written; `git push` denied (`permission_denials`) |
| Read profile cannot write | not yet exercised in a real run | real call: `Write` denied, `Read` allowed — also with a project `.claude/settings.json` allowing `Write` (`--setting-sources ""`) |
| State dir unreadable | path verification (per v0.1 findings) | real call: `Read` of `~/.semipilot/state/…` denied |
| Error-text patterns | seeded, **unverified** — see [design/copilot-cli-findings.md](design/copilot-cli-findings.md) | from Claude Code's documented error messages |
| Whole loop against a fake CLI (every guardrail, outages, quota, rollback, resume) | 56 orchestrator tests | the same 56 + 3 Claude-only (structured errors, cost) |

Do one supervised run on a throwaway feature before relying on a harness, and look for calls classified `unknown`
in `.semipilot/runs/<run>/` — their signature belongs in `failure_patterns`.

## Cost and speed

Every call is a fresh agent session: no context carries over, by design. That makes each call pay the harness's
startup context: on Claude Code 2.1.304 a call that only replies "OK" was measured at $0.07–$0.18 (its system prompt
and tool definitions; the lower figure with the prompt cache warm). A typical feature makes 1 questions call,
1–2 planner calls, 2–4 critic calls, 1 test-writer call and 1–3 implementer calls per task. Preflight and `doctor`
make no model call of their own (`doctor --live` does, on request).

Measure first: on Claude Code the report shows the run's cost and the cost **by role**. Then, in order of effect:

1. **Fewer retries.** Each retry is a whole new session. Tight acceptance criteria, small tasks and a filled-in
   `AGENTS.md` cut more cost than anything below.
2. **The knowledge layer.** Agents read the resolved cards instead of searching the codebase — the biggest saving on
   long implementer calls.
3. **A model per role** (`models:`). Keep your strongest model on the planner and critics; they decide what gets built.
   The implementer works against locked tests and your checks, so a cheaper model there is the usual first step — and
   the one where a quality drop is caught (more retries or blocked tasks show up in the report).
4. **Smaller startup context** (Claude Code): `harnesses.claude.bare: true` passes `--bare` (no hooks, plugins, MCP
   servers or memory files at startup). It needs `ANTHROPIC_API_KEY`; bare mode does not use a subscription login.
5. **Caps for the worst case:** `budget.max_iterations`, `budget.wall_clock_seconds`,
   `harnesses.claude.max_turns.write`, `harnesses.claude.max_budget_usd_per_call` (`--max-budget-usd`).

Not worth cutting: the questions pass and the two critic gates. They are the cheapest calls and they prevent the most
expensive failure — a whole branch built on a wrong reading.

## Switching harness

```bash
semipilot init --harness claude      # updates only the `harness:` line of an existing config, installs the skills
semipilot doctor
```

Nothing else changes: requirements, plans, reports and the knowledge layer are harness-neutral. A run started on one
harness can be resumed on the other.

## Instructions files

Make `AGENTS.md` the source of truth — both harnesses read it. Notes:

- Claude Code reads `AGENTS.md` only when there is **no** `CLAUDE.md`. If you have a `CLAUDE.md`, add the line
  `@AGENTS.md` to it (`semipilot doctor` checks this).
- If your instructions live only in `.github/copilot-instructions.md` and the harness is Claude Code, `init` creates a
  one-line `CLAUDE.md` importing it.
- Path-scoped `.github/instructions/*.instructions.md` files load automatically in Copilot; the loop's prompts tell
  every agent to read the ones whose `applyTo` matches, so they apply on Claude Code too.

## Adding another harness

One adapter class (command line, answer parsing) and one config block (allow/deny rules, failure patterns). See
[architecture.md](architecture.md#adding-a-harness). Candidates with suitable headless modes: OpenAI Codex
(`codex exec --json --sandbox …`), Gemini CLI (`gemini -p --output-format json`), OpenCode (`opencode run`).
