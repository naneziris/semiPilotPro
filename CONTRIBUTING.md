# Contributing

Thanks for helping. semiPilot is small on purpose; changes that keep it that way are the easiest to accept.

## Set up

```bash
git clone https://github.com/naneziris/semiPilotPro && cd semiPilotPro
git checkout v5
pip install -e ".[dev]"
pytest -q                               # the whole suite, ~3 minutes; no agent CLI or network needed
```

The tests run against `tests/fake_agent.py`, a fake agent CLI that speaks both the Copilot and the Claude Code
dialect and follows a per-test scenario. Every orchestrator test runs once per harness.

## Where things go

| Change | Where | Also |
|---|---|---|
| Loop behaviour, guardrails | `src/semipilot/orchestrator.py` | a test in `tests/test_orchestrator.py` (runs on both harnesses) |
| A harness's command line or output parsing | `src/semipilot/harness.py` | `tests/test_runner.py`; a real-CLI check (below) |
| Defaults, permission rules, failure patterns | `src/semipilot/defaults.yaml` | `docs/configuration.md` / `docs/harnesses.md` |
| What an unattended role is told | `src/semipilot/roles/`, `src/semipilot/prompts/` | keep output formats — they are parsed |
| Interactive behaviour | `skills/<skill>/` | `tests/test_skills.py` (format checks) |
| Knowledge-layer tooling | `skills/semipilot-knowledge/scripts/kb.py` | `tests/test_kb.py`; standard library only |
| A new harness | see [docs/architecture.md](docs/architecture.md#adding-a-harness) | |

## Rules

- **Guarantees are enforced in code, not prompts.** If a rule matters, the orchestrator checks it after the call.
- **No new runtime dependencies** without a very good reason: the tool must keep running from a plain download.
  `kb.py` must stay standard-library only.
- **Python 3.9 compatible.**
- **Real-CLI changes need a real check.** When you change what a harness adapter emits, verify the flags against the
  CLI's `--help`, run one health call, one write-profile call that must be denied `git push`, and one read-profile
  call that must be denied a write. Say in the PR what you ran and on which CLI version.
- **Docs move with code.** A changed flag, key or behaviour updates the matching page in `docs/` and the
  `CHANGELOG.md` *Unreleased* section.
- **Versions move together:** `src/semipilot/__init__.py`, every `SKILL.md` `metadata.version`,
  `.claude-plugin/*.json` (a test checks).

## Pull requests

One topic per PR, with tests. Describe the user-visible effect first. CI must be green: tests on Linux and macOS
(Python 3.9 and 3.12).
