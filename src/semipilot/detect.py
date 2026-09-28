"""Stack detection for `semipilot init`: turn what's in the repo into the `checks` list and test patterns.

Deliberately conservative — it only proposes commands that the repo itself declares (package.json scripts,
pyproject tool sections, go.mod, a Makefile). Anything it can't see becomes a `# TODO` the user fills in.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Detected:
    stack: str = "unknown"
    checks: list = field(default_factory=list)       # [{"name", "cmd"}]
    test_patterns: list = field(default_factory=list)
    commands: dict = field(default_factory=dict)      # for copilot-instructions.md: build/test/lint
    notes: list = field(default_factory=list)


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _pyproject_has(p: Path, section: str) -> bool:
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return False
    return re.search(rf"^\[tool\.{re.escape(section)}", text, re.MULTILINE) is not None or \
        re.search(rf"^{re.escape(section)}\b", text, re.MULTILINE) is not None


def detect(repo: Path) -> Detected:
    repo = Path(repo)
    d = Detected()
    pkg = repo / "package.json"
    pyproject = repo / "pyproject.toml"
    gomod = repo / "go.mod"
    makefile = repo / "Makefile"

    if pkg.exists():
        d.stack = "node"
        scripts = (_read_json(pkg).get("scripts") or {})
        deps = {**(_read_json(pkg).get("dependencies") or {}), **(_read_json(pkg).get("devDependencies") or {})}
        pm = "pnpm" if (repo / "pnpm-lock.yaml").exists() else "yarn" if (repo / "yarn.lock").exists() else "npm"
        run = f"{pm} run" if pm != "yarn" else "yarn"
        if "lint" in scripts:
            d.checks.append({"name": "lint", "cmd": f"{run} lint"})
            d.commands["lint"] = f"{run} lint"
        if "typecheck" in scripts:
            d.checks.append({"name": "typecheck", "cmd": f"{run} typecheck"})
        elif (repo / "tsconfig.json").exists():
            d.checks.append({"name": "typecheck", "cmd": "npx tsc --noEmit"})
        if "vitest" in deps:
            d.checks.append({"name": "tests", "cmd": "npx vitest run {task_tests}"})
            d.commands["test"] = "npx vitest run"
        elif "jest" in deps:
            d.checks.append({"name": "tests", "cmd": "npx jest {task_tests}"})
            d.commands["test"] = "npx jest"
        elif "test" in scripts:
            d.checks.append({"name": "tests", "cmd": f"{run} test -- {{task_tests}}"})
            d.commands["test"] = f"{run} test"
            d.notes.append("tests: `npm test -- <files>` assumed to accept file arguments; adjust if not")
        if "build" in scripts:
            d.checks.append({"name": "build", "cmd": f"{run} build"})
            d.commands["build"] = f"{run} build"
        d.test_patterns = ["**/*.test.ts", "**/*.test.tsx", "**/*.test.js", "**/*.spec.ts", "**/*.spec.tsx", "**/__tests__/**"]
    elif pyproject.exists() or (repo / "setup.py").exists() or (repo / "requirements.txt").exists():
        d.stack = "python"
        if pyproject.exists() and _pyproject_has(pyproject, "ruff"):
            d.checks.append({"name": "lint", "cmd": "ruff check ."})
            d.commands["lint"] = "ruff check ."
        if pyproject.exists() and _pyproject_has(pyproject, "mypy"):
            d.checks.append({"name": "typecheck", "cmd": "mypy ."})
        d.checks.append({"name": "tests", "cmd": "python -m pytest -q {task_tests}"})
        d.commands["test"] = "python -m pytest -q"
        d.test_patterns = ["tests/**/*.py", "test/**/*.py", "**/test_*.py", "**/*_test.py"]
    elif gomod.exists():
        d.stack = "go"
        d.checks.append({"name": "vet", "cmd": "go vet ./..."})
        d.checks.append({"name": "tests", "cmd": "go test ./..."})
        d.checks.append({"name": "build", "cmd": "go build ./..."})
        d.commands.update({"test": "go test ./...", "build": "go build ./..."})
        d.test_patterns = ["**/*_test.go"]
        d.notes.append("go: per-task test scoping is not supported; the full package set runs every time")
    elif makefile.exists():
        d.stack = "make"
        text = makefile.read_text(encoding="utf-8", errors="ignore")
        for target in ("lint", "typecheck", "test", "build"):
            if re.search(rf"^{target}:", text, re.MULTILINE):
                name = "tests" if target == "test" else target
                d.checks.append({"name": name, "cmd": f"make {target}"})
                d.commands[target] = f"make {target}"
        d.test_patterns = ["tests/**", "test/**"]
        d.notes.append("make: tests are not scoped per task ({task_tests} unused); fine, just slower")

    if not d.checks:
        d.checks = [{"name": "tests", "cmd": "# TODO: your test command, e.g. `npm test -- {task_tests}` or `pytest -q {task_tests}`"}]
        d.notes.append("no stack detected: fill in `checks` in .semipilot/config.yaml before running")
    if not d.test_patterns:
        d.test_patterns = ["tests/**", "test/**"]
    return d
