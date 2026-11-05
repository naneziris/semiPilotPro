"""`semipilot init` — make a project ready in one command, for one or both supported harnesses.

Writes (never overwrites your config or your instructions; --force refreshes only the skill folders):
    .semipilot/config.yaml          the one file you edit: harness, checks, test patterns (detected)
    .semipilot/.gitignore           keeps run logs out of git
    <skills folder>/semipilot-*/    the skill pack, where the harness's chat finds it:
                                      copilot → .agents/skills/   (VS Code Copilot chat + Copilot CLI)
                                      claude  → .claude/skills/   (Claude Code)
    AGENTS.md                       one-page instructions every agent reads (only if no instructions file exists)
    CLAUDE.md                       `@.github/copilot-instructions.md` — only for Claude Code when that is your only
                                    instructions file (Claude Code reads AGENTS.md or CLAUDE.md, not Copilot's file)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from ._yaml import yaml
from .config import SEMIPILOT_DIR, Layout, instructions_file, kb_flavor, knowledge_layer_present
from .detect import Detected, detect
from .harness import ALIASES, HARNESSES
from .skills_pack import SKILL_DIRS, install_skills, template

LEGACY_FILES = {
    ".github/agents/pilotinloop-planner.agent.md": "PilotInLoop roles are inlined into every call since v0.2",
    ".github/agents/pilotinloop-spec-critic.agent.md": "PilotInLoop roles are inlined into every call since v0.2",
    ".github/agents/pilotinloop-plan-critic.agent.md": "PilotInLoop roles are inlined into every call since v0.2",
    ".github/prompts/refine-requirements.prompt.md": "replaced by the semipilot-refine skill (/semipilot-refine)",
    ".github/prompts/spec-critic.prompt.md": "replaced by the semipilot-spec-critic skill (/semipilot-spec-critic)",
    ".github/agents/refiner.agent.md": "replaced by the semipilot-refine skill",
    ".github/agents/spec-critic.agent.md": "replaced by the semipilot-spec-critic skill",
}


def normalize_harness(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = ALIASES.get(name.strip().lower(), name.strip().lower())
    if n not in HARNESSES:
        raise SystemExit(f"semipilot: unknown harness {name!r}; supported: {', '.join(sorted(HARNESSES))}")
    return n


def pick_harness(repo: Path, explicit: Optional[str]) -> tuple[str, str]:
    """(harness, why). Explicit flag > existing config > the only agent CLI on PATH > copilot."""
    if explicit:
        return normalize_harness(explicit), "--harness"
    cfg_file = Path(repo) / SEMIPILOT_DIR / "config.yaml"
    if cfg_file.exists():
        user = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        if user.get("harness"):
            return normalize_harness(str(user["harness"])), "existing config"
    has = {h: shutil.which(cls.default_command) is not None for h, cls in HARNESSES.items()}
    if has.get("claude") and not has.get("copilot"):
        return "claude", "only `claude` is on PATH"
    return "copilot", "default" if not has.get("copilot") else "`copilot` is on PATH"


def config_template(d: Detected, harness: str) -> str:
    """The user-facing config: short, commented, only what they might need to touch."""
    checks_yaml = yaml.safe_dump(d.checks, sort_keys=False, default_flow_style=False).rstrip()
    patterns_yaml = yaml.safe_dump(d.test_patterns, default_flow_style=False).rstrip()
    notes = "".join(f"# note: {n}\n" for n in d.notes)
    return f"""# semipilot — project configuration (detected stack: {d.stack})
# Everything not listed here has a built-in default; `semipilot config` prints the full effective config.
{notes}
# The agent CLI that runs the unattended loop: copilot (GitHub Copilot CLI) | claude (Claude Code).
harness: {harness}

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
#   model: null            # pin a model for every loop call, or leave the CLI default
# models:                  # a model per role (null = runner.model); keep planner/critics strong, measure before
#   implementer: null      # switching — the report shows cost by role
# budget:
#   max_iterations: 30     # implementer calls per run
#   wall_clock_seconds: 21600
"""


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def agents_md(repo: Path, d: Detected) -> str:
    return (template("AGENTS.template.md")
            .replace("{{REPO_NAME}}", repo.name)
            .replace("{{BUILD}}", d.commands.get("build", "{{TODO: build command, or 'none'}}"))
            .replace("{{TEST}}", d.commands.get("test", "{{TODO: test command}}"))
            .replace("{{LINT}}", d.commands.get("lint", "{{TODO: lint command, or 'none'}}")))


def _write(dest: Path, content: str, report: list, force: bool = False) -> bool:
    if dest.exists() and not force:
        report.append(("skip", dest))
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    report.append(("write", dest))
    return True


def set_harness_line(cfg_file: Path, harness: str) -> bool:
    """Point an existing config at another harness, changing only the `harness:` line."""
    text = cfg_file.read_text(encoding="utf-8")
    if re.search(r"^harness:\s*\S+", text, re.MULTILINE):
        new = re.sub(r"^harness:\s*\S+.*$", f"harness: {harness}", text, count=1, flags=re.MULTILINE)
    else:
        new = f"harness: {harness}\n\n" + text
    if new != text:
        cfg_file.write_text(new, encoding="utf-8")
        return True
    return False


PRIVATE_BLOCK = """
# Trial mode: semipilot's own files and `git.local_paths` stay local — listed in .git/info/exclude, never committed;
# a run branch holds only the feature's code. Set `private: false` (and empty local_paths) when the team adopts it.
private: true
"""
LOCAL_PATHS_DEFAULT = [".github/"]


def set_private(cfg_file: Path, local_paths: Optional[list] = None) -> bool:
    """Turn on `private: true` and add `git.local_paths` in an existing config, editing only those lines.
    Returns True when the file changed."""
    text = cfg_file.read_text(encoding="utf-8")
    new = text
    if re.search(r"^private:\s*\S+", new, re.MULTILINE):
        new = re.sub(r"^private:\s*\S+.*$", "private: true", new, count=1, flags=re.MULTILINE)
    else:
        new = new.rstrip("\n") + "\n" + PRIVATE_BLOCK
    paths = LOCAL_PATHS_DEFAULT if local_paths is None else local_paths
    if paths and not re.search(r"^\s+local_paths:", new, re.MULTILINE):
        items = "".join(f'    - "{p}"\n' for p in paths)
        block = ("  # your own uncommitted changes that must stay uncommitted (files, folders ending in /, globs)\n"
                 f"  local_paths:\n{items}")
        if re.search(r"^git:\s*$", new, re.MULTILINE):
            new = re.sub(r"^git:\s*$", "git:\n" + block.rstrip("\n"), new, count=1, flags=re.MULTILINE)
        else:
            new = new.rstrip("\n") + "\ngit:\n" + block
    if new != text:
        cfg_file.write_text(new, encoding="utf-8")
        return True
    return False


def init(repo: Path, force: bool = False, harness: Optional[str] = None,
         skills_for: Optional[list] = None, private: bool = False) -> tuple[Detected, list, dict]:
    """Returns (detected stack, [(action, path)], info) where info has harness, why, skills_for, notes."""
    repo = Path(repo).resolve()
    lay = Layout(repo)
    report: list = []
    d = detect(repo)
    h, why = pick_harness(repo, harness)
    chats = [normalize_harness(x) for x in (skills_for or [h])]
    notes: list = []
    if knowledge_layer_present(repo, {}):
        notes.append("knowledge layer detected (docs/cards + scripts/kb): the skills and the loop use it; run the "
                     "semipilot-scribe skill after each review")
        if kb_flavor(repo) == "node":
            notes.append("the knowledge layer still uses the Node scripts — `semipilot kb init --force` adds "
                         "scripts/kb/kb.py and switches the hook and CI to it (cards untouched)")

    if lay.config.exists():  # the one file the user edits: never overwritten, not even with --force
        report.append(("skip", lay.config))
        if harness and set_harness_line(lay.config, h):
            report[-1] = ("update", lay.config)
    else:
        _write(lay.config, config_template(d, h), report)
    if private and set_private(lay.config) and report and report[-1] == ("skip", lay.config):
        report[-1] = ("update", lay.config)
    _write(lay.root / ".gitignore", "runs/\nlast-run\n", report)
    lay.features.mkdir(parents=True, exist_ok=True)

    for c in dict.fromkeys(chats):
        report += install_skills(repo, c, force=force)

    main = instructions_file(repo, {})
    if not (repo / main).exists():
        _write(repo / "AGENTS.md", agents_md(repo, d), report)
        main = "AGENTS.md"
    if "claude" in chats or h == "claude":
        claude_md = repo / "CLAUDE.md"
        if main == ".github/copilot-instructions.md" and not (repo / "AGENTS.md").exists() and not claude_md.exists():
            _write(claude_md, "@.github/copilot-instructions.md\n", report)
        elif claude_md.exists() and (repo / "AGENTS.md").exists() and "AGENTS.md" not in claude_md.read_text(encoding="utf-8"):
            notes.append("CLAUDE.md exists, so Claude Code will not read AGENTS.md — add a line `@AGENTS.md` to CLAUDE.md")
    rc = ((yaml.safe_load(lay.config.read_text(encoding="utf-8")) or {}).get("runner") or {}) if lay.config.exists() else {}
    if rc.get("command") and Path(str(rc["command"]).split()[0]).name != HARNESSES[h].default_command:
        notes.append(f"runner.command in .semipilot/config.yaml is {rc['command']!r}, which overrides the {h} harness's "
                     f"executable — remove it, or set harnesses.{h}.command instead")
    if any(r[0] == "update" and SKILL_DIRS[c] in str(r[1]) for r in report for c in chats):
        notes.append("semipilot-* skill folders from another version were replaced (`git diff` shows any local edits)")
    for path, why_legacy in LEGACY_FILES.items():
        if (repo / path).exists():
            notes.append(f"{path} is no longer used ({why_legacy}); delete it when you are ready")
    cfg_now = yaml.safe_load(lay.config.read_text(encoding="utf-8")) or {} if lay.config.exists() else {}
    if cfg_now.get("private") or ((cfg_now.get("git") or {}).get("local_paths")):
        from .config import load_config, local_set, sync_excludes
        excl = sync_excludes(repo, load_config(repo))
        ls = local_set(repo, load_config(repo))
        if cfg_now.get("private"):
            notes.append("private mode: semipilot's files are listed in "
                         f"{excl if excl else '.git/info/exclude'} and never committed — `git status` stays clean")
        if ls.user:
            notes.append(f"kept local (never committed, agents may not change them): {', '.join(ls.user)}")
    if len(set(chats)) > 1:
        notes.append("skills installed in both .agents/skills and .claude/skills; Copilot CLI reads both folders and "
                     "may list each semipilot skill twice (same content)")
    return d, report, {"harness": h, "why": why, "skills_for": list(dict.fromkeys(chats)), "notes": d.notes + notes,
                       "instructions": main}


def skills_dirs_for(chats: list) -> list:
    return [SKILL_DIRS[c] for c in chats]
