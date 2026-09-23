# Copilot CLI verification (handoff §4.2, build-order step 1)

Checked against the GitHub Docs programmatic reference and current release notes (Sept 2026). Items marked
**unverified** are not documented and must be confirmed by running the real CLI once; the runner is built so
they can be adjusted in `config.yaml` without code changes.

| Question | Finding | Used as |
|---|---|---|
| Non-interactive single prompt that exits when done | `copilot -p "<prompt>"`. `-s` suppresses stats/decoration so stdout is only the agent's response. `--no-ask-user` stops it pausing for input. | `runner.build_command` |
| Session behaviour | Sessions are resumed only via `--resume [id]` / `--continue` (opt-in). A plain `-p` invocation is a fresh session. The CLI rejects `--continue` combined with `--resume`. | Runner refuses `--resume`, `--continue`, `--session-id`, `-r` (hard-coded + config list); tested. |
| Tool permissions | `--allow-tool=<kind>[(filter)]`, `--deny-tool=...`; kinds: `shell`, `write`, `read`, `url`, `memory`, `<mcp-server>`. Shell filters match command + first-level subcommand, e.g. `shell(git push)`. **Deny takes precedence** over allow and `--allow-all-tools`. | Per-role allow lists + global deny list in `config.yaml`. |
| Path restriction | Files outside cwd need `--add-dir`; `--allow-all-paths` disables verification. | `plan.json` is kept outside the repo so the implementer physically cannot read it. Never pass `--add-dir` for the state dir. |
| Model selection | `--model=<id>`; precedence: custom agent's model > `--model` > `COPILOT_MODEL` > settings.json > default. | `runner.model` (null = default). |
| Custom agents / prompts / skills in headless mode | `--agent=<name>` loads a repo/user custom agent; custom instructions are honoured (there is a `--no-custom-instructions` opt-out, so the default is on). Skills and plugins load per the normal discovery rules. | `runner.agents` maps roles to existing SemiPilotPro agents. |
| Output capture | stdout = response (with `-s`); `--output-format json` gives JSONL events; `--log-dir` writes CLI logs; `--share=PATH` exports the session transcript to Markdown after completion. | Runner captures stdout/stderr per call and passes `--log-dir runs/<run_id>/cli`. Consider adding `--share=runs/<run_id>/<label>-transcript.md` for morning debugging (**unverified** that it works with `-s`). |
| Exit codes | Non-zero on failure; the specific codes for 5xx/429/401 are **not documented**. | Classification is regex on exit code + stdout + stderr (`failure_patterns`). Unknown non-zero → transient once, then task failure, raw output logged. |
| 5xx / 429 / network / auth text | **Unverified.** Patterns seeded with obvious strings (`502`, `429`, `ECONNRESET`, `401`, `token expired`, ...). | Extend after the first real outage; `runs/<run_id>/*-infra*.log` keep the raw text. |
| Token expiry | Not exposed by the CLI. Auth tokens come from `copilot login` (device flow) or `COPILOT_GITHUB_TOKEN` / `GH_TOKEN` / `GITHUB_TOKEN`. | Preflight: trivial CLI call + optional `gh auth status`; optional `COPILOT_TOKEN_EXPIRES_AT` env var for PATs with known expiry. |
| Quota / credits | Copilot CLI consumes premium requests / AI credits per prompt; there is a per-session "AI credit limit" setting. Exhaustion text is **unverified**. | Separate `quota_exhausted` class → halt immediately (never backoff). Preflight prints an upper bound on requests for the run and can run an optional `quota_check_cmd`. |
| Autopilot / max-turns | The CLI has autopilot continuation and (via the Actions wrapper) a max-turns option. | Not used: the orchestrator owns the loop; one task per process is the guardrail. |

**Action for the first real dry run:** run `pilotinloop` on the dummy feature, then grep `runs/<run_id>/` for any
call classified `unknown` and add its stderr signature to `failure_patterns`.
