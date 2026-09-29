"""`semipilot init` — make a repository ready in one command.

Writes (never overwrites):
    .semipilot/config.yaml                    the one file the user edits (checks + test patterns, detected)
    .semipilot/.gitignore                     keeps run logs out of git
    .github/prompts/refine-requirements.prompt.md   /refine-requirements in Copilot chat (@refiner)
    .github/prompts/spec-critic.prompt.md           /spec-critic in Copilot chat (Gate 1 + approval)
    .github/agents/{refiner,spec-critic,pilotinloop-*}.agent.md   the agents behind the prompts and the loop
    .github/copilot-instructions.md           one-page repo instructions (only if missing), with detected commands
"""
from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from ._yaml import yaml

from .config import SEMIPILOT_DIR, Layout, knowledge_layer_present
from .detect import Detected, detect


def _asset(*parts: str) -> str:
    return resources.files("semipilot").joinpath("assets", *parts).read_text(encoding="utf-8")


def _write(dest: Path, content: str, report: list, force: bool = False) -> bool:
    if dest.exists() and not force:
        report.append(("skip", dest))
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    report.append(("write", dest))
    return True


def config_template(d: Detected) -> str:
    """The user-facing config: short, commented, only what they might need to touch."""
    checks_yaml = yaml.safe_dump(d.checks, sort_keys=False, default_flow_style=False).rstrip()
    patterns_yaml = yaml.safe_dump(d.test_patterns, default_flow_style=False).rstrip()
    notes = "".join(f"# note: {n}\n" for n in d.notes)
    return f"""# semipilot — repository configuration (detected stack: {d.stack})
# Everything not listed here has a built-in default; run `semipilot config` to see the full effective config.
{notes}
# The commands that define "done". All must pass after every task, fastest first.
# Keep `{{task_tests}}` in the test command: it expands to the current task's locked test files
# (and is empty for the final full-suite run).
checks:
{_indent(checks_yaml, 2)}

tests:
  # Files matching these globs are locked after the test-writing stage; the implementer cannot change them.
  patterns:
{_indent(patterns_yaml, 4)}

# runner:
#   model: null            # pin a Copilot model id, or leave the CLI default
# budget:
#   max_iterations: 30     # implementer calls per run
#   wall_clock_seconds: 21600
"""


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def instructions_template(repo: Path, d: Detected) -> str:
    text = _asset("copilot-instructions.md")
    return (text.replace("{{REPO_NAME}}", repo.name)
            .replace("{{BUILD}}", d.commands.get("build", "<build command>"))
            .replace("{{TEST}}", d.commands.get("test", "<test command>"))
            .replace("{{LINT}}", d.commands.get("lint", "<lint command, or 'none'>")))


def init(repo: Path, force: bool = False) -> tuple[Detected, list]:
    repo = Path(repo).resolve()
    lay = Layout(repo)
    report: list = []
    d = detect(repo)
    if knowledge_layer_present(repo, {}):
        d.notes.append("knowledge layer detected (docs/cards + scripts/kb): the refiner, critics and the loop will use it; run @scribe after each review")

    _write(lay.config, config_template(d), report, force)
    _write(lay.root / ".gitignore", "runs/\nlast-run\n", report, force)
    lay.features.mkdir(parents=True, exist_ok=True)

    prompts_dir = repo / ".github" / "prompts"
    agents_dir = repo / ".github" / "agents"
    for name in ("refine-requirements.prompt.md", "spec-critic.prompt.md"):
        _write(prompts_dir / name, _asset("prompts", name), report, force)
    for entry in sorted(resources.files("semipilot").joinpath("assets", "agents").iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".agent.md"):
            _write(agents_dir / entry.name, entry.read_text(encoding="utf-8"), report, force)

    instr = repo / ".github" / "copilot-instructions.md"
    if not instr.exists():
        _write(instr, instructions_template(repo, d), report)
    else:
        report.append(("skip", instr))
    return d, report


def which(cmd: str) -> str | None:
    return shutil.which(cmd)
