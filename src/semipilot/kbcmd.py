"""`semipilot kb …` — install the knowledge layer, and run its tool.

    semipilot kb init [--system <prefix>] [--force]     install scripts, templates, hook and CI into the project
    semipilot kb validate | index [--check] | resolve --tags a,b | drift | guard | catchup [--mark]

`kb init` never overwrites knowledge content (cards, vocabulary, docs, instructions). `--force` refreshes only the
mechanical files semipilot owns: scripts/kb/kb.py, the pre-commit hook and the CI workflow — which is also how a
knowledge layer installed with the earlier Node scripts is upgraded.
"""
from __future__ import annotations

import os
import re
import runpy
import stat
import subprocess
import sys
from pathlib import Path

from .config import instructions_file
from .skills_pack import kb_script, template

ROUTER_MARKERS = ("semipilot:knowledge-router", "Repo knowledge router")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "app"


def _git_prefix(project: Path) -> tuple[Path, str]:
    """(git root, project path inside it with trailing slash or '')."""
    r = subprocess.run(["git", "rev-parse", "--show-toplevel", "--show-prefix"], cwd=project, capture_output=True, text=True)
    if r.returncode != 0:
        return project, ""
    lines = r.stdout.splitlines()
    return Path(lines[0]), (lines[1].strip() if len(lines) > 1 else "")


def kb_init(project: Path, system: str = "", force: bool = False) -> tuple[list, list]:
    project = Path(project).resolve()
    system = _slug(system or project.name)
    root, prefix = _git_prefix(project)
    report: list = []
    notes: list = []

    def put(rel_dest: Path, content: str, mechanical: bool = False, executable: bool = False) -> None:
        dest = rel_dest
        if dest.exists() and not (force and mechanical):
            report.append(("skip", dest))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        existed = dest.exists()
        dest.write_text(content, encoding="utf-8")
        if executable:
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        report.append(("update" if existed else "write", dest))

    def sub(text: str) -> str:
        return text.replace("{{SYSTEM}}", system).replace("{{REPO_NAME}}", project.name)

    put(project / "scripts/kb/kb.py", kb_script().read_text(encoding="utf-8"), mechanical=True, executable=True)
    put(project / "scripts/kb/kb.config.json", template("kb.config.json"))
    put(project / ".githooks/pre-commit", template("pre-commit"), mechanical=True, executable=True)
    # one workflow per project: a second project in the same monorepo gets its own file, never the first one's
    wf_name = "knowledge-layer.yml" if not prefix else f"knowledge-layer-{_slug(prefix.rstrip('/'))}.yml"
    put(root / ".github/workflows" / wf_name,
        template("knowledge-layer.yml").replace("{{PROJECT_DIR}}", prefix.rstrip("/") or ".")
        .replace("name: Knowledge Layer", f"name: Knowledge Layer{' (' + prefix.rstrip('/') + ')' if prefix else ''}"),
        mechanical=True)
    put(project / "docs/cards/_vocabulary.md", sub(template("_vocabulary.template.md")))
    put(project / "docs/cards/_templates/card.template.md", sub(template("card.template.md")))
    put(project / "docs/cards/_templates/area.instructions.template.md", sub(template("area.instructions.template.md")))
    put(project / "docs/README.md", sub(template("docs-README.template.md")))
    put(project / "docs/decisions.md", sub(template("decisions.template.md")))
    put(project / "docs/dependencies.md", sub(template("dependencies.template.md")))
    put(project / "docs/CHANGELOG.md", sub(template("CHANGELOG.template.md")))

    # AGENTS.md: the instructions every harness reads, ending with the knowledge router.
    router = template("AGENTS-router-block.md")
    agents = project / "AGENTS.md"
    main = instructions_file(project, {})
    if not agents.exists():
        if (project / main).exists():  # e.g. only .github/copilot-instructions.md: keep it the source of truth
            body = (f"# {project.name} — instructions for coding agents\n\nRepository conventions, commands and invariants: "
                    f"`{main}` (single source of truth — this file only points there).\n")
        else:
            body = sub(template("AGENTS.template.md")).replace("{{BUILD}}", "{{TODO: build command}}") \
                .replace("{{TEST}}", "{{TODO: test command}}").replace("{{LINT}}", "{{TODO: lint command}}")
        put(agents, body.rstrip() + "\n" + router)
    else:
        text = agents.read_text(encoding="utf-8")
        if any(m in text for m in ROUTER_MARKERS):
            report.append(("skip", agents))
        else:
            agents.write_text(text.rstrip() + "\n" + router, encoding="utf-8")
            report.append(("update", agents))

    legacy = sorted((project / "scripts/kb").glob("kb-*.mjs"))
    if legacy:
        notes.append(f"{len(legacy)} Node scripts (scripts/kb/kb-*.mjs) from an earlier install are no longer needed "
                     "once the hook and CI use kb.py" + ("" if force else " — run `semipilot kb init --force` to switch them")
                     + "; delete the .mjs files and any kb:* entries in package.json afterwards")
    hooks_path = f"{prefix}.githooks" if prefix else ".githooks"
    current = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=project, capture_output=True, text=True).stdout.strip()
    if current and current != hooks_path:
        notes.append(f"core.hooksPath is already {current!r} (another hook manager?) — setting it to {hooks_path} would "
                     f"replace those hooks; call .githooks/pre-commit from your existing pre-commit hook instead")
    else:
        notes.append(f"activate the hook once per clone: git config core.hooksPath {hooks_path}")
    if prefix:
        notes.append(f"the CI workflow went to the repository root (.github/workflows/{wf_name}) and runs in {prefix.rstrip('/')}")
    return report, notes


def run_kb(project: Path, args: list) -> int:
    """Run the project's scripts/kb/kb.py (or the bundled one) with `--root <project>`."""
    project = Path(project).resolve()
    script = project / "scripts/kb/kb.py"
    if not script.exists():
        script = kb_script()
    argv = [str(script), "--root", str(project), *args]
    old_argv, old_cwd = sys.argv, os.getcwd()
    try:
        sys.argv = argv
        os.chdir(project)
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        return int(e.code or 0) if not isinstance(e.code, str) else 1
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
    return 0
