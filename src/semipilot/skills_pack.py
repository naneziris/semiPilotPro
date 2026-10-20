"""The semiPilot skill pack: where the skills live, and copying them into a project for a harness.

Skills are plain Agent Skills folders (`<name>/SKILL.md` + `references/`, `examples/`, `scripts/`, `assets/`). They
are the single source of truth for everything an agent does interactively and for the knowledge-layer tooling
(`semipilot-knowledge/scripts/kb.py`, `semipilot-knowledge/assets/templates/`).

Lookup order: the copy packaged inside the installed wheel (`semipilot/skills`), then the repository's top-level
`skills/` folder (running from a checkout or a download with `bin/semipilot`).
"""
from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path
from typing import Optional

SKILLS = ("semipilot-refine", "semipilot-spec-critic", "semipilot-run", "semipilot-scribe", "semipilot-knowledge")

# Project-level skill folders each harness's chat reads (and the CLI where it differs).
#   GitHub Copilot — VS Code chat (Copilot harness) and Copilot CLI both read `.agents/skills/` (also `.github/skills/`);
#   Claude Code    — reads `.claude/skills/` only.
SKILL_DIRS = {"copilot": ".agents/skills", "claude": ".claude/skills"}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "Thumbs.db")


def skills_root() -> Path:
    try:
        packaged = Path(str(resources.files("semipilot").joinpath("skills")))
        if (packaged / "semipilot-refine" / "SKILL.md").exists():
            return packaged
    except (ModuleNotFoundError, TypeError):  # pragma: no cover
        pass
    checkout = Path(__file__).resolve().parents[2] / "skills"
    if (checkout / "semipilot-refine" / "SKILL.md").exists():
        return checkout
    raise FileNotFoundError("semipilot's skills/ folder is missing — reinstall, or keep the downloaded folder whole")


def skill_path(name: str) -> Path:
    return skills_root() / name


def kb_script() -> Path:
    return skill_path("semipilot-knowledge") / "scripts" / "kb.py"


def template(name: str) -> str:
    return (skill_path("semipilot-knowledge") / "assets" / "templates" / name).read_text(encoding="utf-8")


def skill_version(skill_dir: Path) -> str:
    """`metadata.version` from a SKILL.md frontmatter ('' when absent or unreadable)."""
    try:
        text = (Path(skill_dir) / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'^\s+version:\s*"?([^"\n]+)"?\s*$', text.split("\n---", 2)[0] if text.startswith("---") else "", re.MULTILINE)
    return m.group(1).strip() if m else ""


def _newer(a: str, b: str) -> bool:
    """True when version a is newer than b (numeric dotted versions; anything unparsable is not newer)."""
    def key(v):
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return None
    ka, kb = key(a), key(b)
    return bool(ka and kb and ka > kb)


def install_skills(project: Path, harness: str, force: bool = False, names: Optional[tuple] = None) -> list:
    """Copy the skills into the harness's project skill folder. Returns [(action, path)].

    semipilot owns the `semipilot-*` folders: an installed copy from another semipilot version is replaced (that is
    how an upgrade reaches the project), and `force` replaces it regardless. A copy of the current version is kept.
    Customise a skill by copying it under your own name, not by editing these folders."""
    dest_root = Path(project) / SKILL_DIRS[harness]
    report = []
    for name in names or SKILLS:
        dest = dest_root / name
        src = skill_path(name)
        installed, packaged = skill_version(dest), skill_version(src)
        if dest.exists() and not force and (installed == packaged or _newer(installed, packaged)):
            report.append(("skip", dest))  # current, or newer than this semipilot (never downgrade silently)
            continue
        action = "update" if dest.exists() else "write"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=IGNORE)
        report.append((action, dest))
    return report
