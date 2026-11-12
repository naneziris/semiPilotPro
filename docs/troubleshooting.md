# Troubleshooting

Start with `semipilot doctor`. Every agent call is logged in `.semipilot/runs/<run-id>/<label>.log` with the
prompt, the agent's answer, stdout, stderr, exit code and classification — that log answers most questions.

## Setup

**`auth_failure` before the run starts, or `doctor --live` fails** — Run the CLI once interactively and log in
(`claude` → `/login`, or `copilot login`). For Claude Code with an API key, set `ANTHROPIC_API_KEY`.

**"Claude Code / GitHub Copilot CLI not found"** — Install it, or set `harnesses.<name>.command` to its full path.

**The skills don't show up in chat.** Check the folder for your chat: `.claude/skills/` for Claude Code,
`.agents/skills/` for Copilot (VS Code chat and CLI). Installed for the other one? `semipilot init --skills both`.
VS Code: `chat.useAgentSkills` must be on (default). Restart the chat session after installing.

**"AGENTS.md filled in [!!]"** — Replace the `{{TODO}}` lines. The plan critic rejects plans while they remain.

**Claude Code ignores AGENTS.md.** You have a `CLAUDE.md`; Claude Code then reads only that. Add a line `@AGENTS.md`.

## Preflight refuses

| Message | Fix |
|---|---|
| `requirements.md not found` | `/semipilot-refine <idea>` in chat |
| `… is not approved on branch X` | `/semipilot-spec-critic`, reply `approve`. If it says *It IS approved on branch Y*, you are on a branch without the approved spec: check out your base branch, or bring the file over as the message shows |
| `acceptance criteria without a machine-checkable [check: …] tag` | Tag each criterion (the refiner's acceptance-criteria guide) |
| `working tree is dirty` | Commit or stash. The check is repository-wide on purpose: rollbacks use `git reset --hard`. Changes you want to keep uncommitted (agent files, local scripts): list them under `git.local_paths` — they are then ignored, never committed and kept through resets |
| `expected_files include …, which the user keeps local` / `BLOCKED: needs package.json` | The feature needs a file in `git.local_paths`: commit your local change to it, or take it out of `local_paths`, then `resume` |
| `'<feature>' already has a run on branch …` | An earlier run was interrupted or stopped: `semipilot resume <feature>`. To start over instead: `git branch -D <branch>`, then `run` |
| `branch … already exists` | A branch of that name exists that no semipilot run made: delete it, or `--branch other-name` |
| `you are on <branch>, the branch of an earlier semipilot run` | `git checkout main`, or `--stack` to build on top of it |
| `knowledge layer unhealthy` | `semipilot kb validate` and fix what it reports |
| `unknown tag(s)` | Fix `Tags:` under Knowledge References in the requirements |
| `check … is still a TODO` | Edit `checks` in `.semipilot/config.yaml` |
| `unknown harness` | `harness: copilot` or `harness: claude` |

## During or after a run

**"argument list too long" / `agent_start_failed`.** Fixed in 0.2.2: with the Copilot harness, prompts above
`harnesses.copilot.prompt_file_threshold` (96 KiB) are written to a file in the run folder that the agent reads,
and failing check output pasted into the next prompt is capped (`check_output_max_bytes`, colour codes stripped,
long lines cut). If it still happens, your shell environment itself is very large (`env | wc -c`); lower the
threshold. Then `semipilot resume <feature>`.

**`nothing to resume`.** No run of the feature has started yet (no checkpoint on any local branch) — use `run`.
Since 0.2.2 `resume` finds the checkpoint on the run branch from whatever branch you are on.

**It ran three times / kept re-running preflight / tried to "ping GitHub".** It was started from inside an agent
session (Copilot CLI, Claude Code, VS Code chat). That agent's shell tool cuts long commands off, and the agent then
retries and diagnoses on its own. Run `run` and `resume` in a plain terminal tab; the CLI prints a note when it
suspects an agent session.

**`plan_rejected`.** Read `rejection-log.md`. Repeated critic rejections usually mean an ambiguous or oversized spec
— fix it and run again (delete the run branch first). If the plan critic says the instructions are empty, fill them.

**A task is blocked: "same error twice".** Read the task's two attempt logs. Typical causes: a locked test that
expects something the spec didn't say (fix the spec, rollback, resume), or an environment problem the agent cannot
fix (a missing service, a flaky test).

**A locked test was changed by the test-fixer.** It may only change imports, names and signatures. The report lists
the edit under *Warnings* — review it like any other diff.

**`auth_failure` mid-run.** The login expired. Log in again and `semipilot resume <feature>`. For long runs on
tokens with a known expiry, set `SEMIPILOT_TOKEN_EXPIRES_AT` so preflight warns you.

**`quota_exhausted`.** Premium requests, usage limit or credit balance ran out. Wait for the reset (or raise the
limit), then `resume`. The interrupted task keeps its attempt count.

**`agent_unavailable`.** The service was down long enough to trip the breaker. `resume` later, or set
`infra.retry_window` to resume once automatically.

**Calls classified `unknown`.** A failure text no pattern recognised: retried once, then counted against the task.
Copy a distinctive fragment of the stderr from the log into your config:

```yaml
failure_patterns:
  transient: ["the distinctive fragment"]     # or fatal / quota_exhausted
```

**`guardrail_violation`.** An agent switched branches despite the deny rules. The loop switched back and stopped;
look at that call's log, then `resume`.

**The final full suite failed although every task passed.** Tasks interfere (shared state, ordering). The report's
warning shows the failure; usually a new requirement or a fix by hand.

**Cost is higher than expected (Claude Code).** Each call is a fresh session and pays Claude Code's startup context.
The report's cost by role shows where it goes; see [harnesses.md](harnesses.md#cost-and-speed) for what to change, in
order of effect.

## Risk tiers, review, cost (0.3)

**The run stopped with `plan_approval` and I did not set a risk tier.** The plan touches a path under
`autonomy.escalate` (auth, billing, payments, migrations, SQL, CI workflows by default). The report's first lines
name the files. Read `implementation-plan.md` and `semipilot approve <feature>`; to change which paths count, set
`autonomy.escalate.medium` to your own list (`[]` for none).

**`semipilot approve` says "not ready for that".** The run is not stopped at a plan-approval gate — `semipilot status`
shows where it is. After a `task_review` stop the command is `semipilot resume`.

**I approved the plan and it asks again.** The plan changed after the approval (a `replan`, or a run that had to
plan again). An approval covers one plan, identified by its hash.

**"its locked tests already pass before any implementation".** Read those test files. Either the test asserts
nothing about the change (sharpen the criterion and start over), or the behaviour already exists (then the
criterion is not new work). `resume` goes on regardless when `red_check` is `halt`.

**The reviewer says `no verdict` / `did not run`.** Its answer had no JSON, or the call failed (quota, outage). The
run itself is unaffected. `semipilot review <feature> --agent` runs it again; the raw answer is in
`.semipilot/runs/<run-id>/reviewer.log`.

**The reviewer's findings are wrong.** They can be: it is an agent grading against a rubric. Verify in the code,
and if a kind of false alarm repeats, edit the rubric (`.semipilot/roles/reviewer.md`).

**Copilot: "The agent CLI reported no usage figures".** No session file with a `session.shutdown` event was found
for the calls under `harnesses.copilot.usage.session_state_dir` (`~/.copilot/session-state`). Check that the folder
exists and gets a new `events.jsonl` when you run `copilot -p "hi" -s`; if your CLI keeps sessions elsewhere, point
the key there. Otherwise try `usage.silent: false` (parses the stats block the CLI prints). Calls and minutes per
role are always reported.

**`semipilot mr`: "cannot tell where issues and merge requests live".** The `origin` URL has neither `github` nor
`gitlab` in it. Set `forge.provider`. **"`glab` not found"**: install the forge's CLI and log in. **"the branch is
pushed, but … could not open the request"**: the message is the CLI's own (often: a request for that branch already
exists); open it by hand, or fix and run `semipilot mr <feature> --force`.

**`semipilot chore` does nothing: "waiting for review".** `chores.max_open` chore branches exist locally and are not
merged into the branch you are on. Merge or delete them (after merging on the forge: pull, then delete the local
branch).

**`semipilot chore`: "the checks fail on the starting branch".** A chore is verified by your checks; on a red base
that is impossible. Fix the base first.

## Knowledge layer

| Error | Fix |
|---|---|
| `tag "x" is not in _vocabulary.md` | Use an existing tag, or add one in a reviewed change |
| `code path does not exist` | The code moved; update the card, then `kb index` |
| `manifest.json is stale` | `semipilot kb index`, commit it |
| `DRIFT undeclared dependency X -> Y` | Add Y to X's `depends_on`, or remove the import |
| `no source files … under src` | Set `srcDirs` / `extensions` in `scripts/kb/kb.config.json` |
| The hook doesn't run | `git config core.hooksPath .githooks` (the path `kb init` printed, in a monorepo) |

## Getting help

Open an issue with the output of `semipilot --version`, `semipilot doctor`, the stop reason, and the relevant call
log (remove anything confidential first).
