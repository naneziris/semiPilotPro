import json
import subprocess
from pathlib import Path

from semipilot.cli import main
from semipilot.detect import detect
from semipilot.initcmd import init


def mkrepo(tmp_path: Path, files: dict) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return repo


def test_detect_node_vitest(tmp_path):
    repo = mkrepo(tmp_path, {"package.json": json.dumps({"scripts": {"lint": "eslint .", "build": "tsc"}, "devDependencies": {"vitest": "1"}}),
                             "tsconfig.json": "{}"})
    d = detect(repo)
    assert d.stack == "node"
    names = [c["name"] for c in d.checks]
    assert names == ["lint", "typecheck", "tests", "build"]
    assert "{task_tests}" in next(c["cmd"] for c in d.checks if c["name"] == "tests")
    assert next(c["cmd"] for c in d.checks if c["name"] == "typecheck") == "npx tsc --noEmit"


def test_detect_python(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": "[tool.ruff]\nline-length = 100\n[tool.mypy]\nstrict = true\n"})
    d = detect(repo)
    assert [c["name"] for c in d.checks] == ["lint", "typecheck", "tests"]


def test_detect_unknown_leaves_todo(tmp_path):
    repo = mkrepo(tmp_path, {"main.rs": ""})
    d = detect(repo)
    assert d.checks[0]["cmd"].startswith("# TODO")
    assert d.notes


def test_init_writes_only_what_is_needed_and_never_overwrites(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": "[project]\nname='x'\n", ".github/copilot-instructions.md": "# mine\n"})
    d, report = init(repo)
    written = sorted(str(p.relative_to(repo)) for a, p in report if a == "write")
    assert written == sorted([
        ".semipilot/config.yaml", ".semipilot/.gitignore",
        ".github/prompts/refine-requirements.prompt.md", ".github/prompts/spec-critic.prompt.md",
        ".github/agents/refiner.agent.md", ".github/agents/spec-critic.agent.md",
        ".github/agents/pilotinloop-planner.agent.md", ".github/agents/pilotinloop-spec-critic.agent.md",
        ".github/agents/pilotinloop-plan-critic.agent.md",
    ])
    assert (repo / ".github/copilot-instructions.md").read_text() == "# mine\n"
    (repo / ".semipilot/config.yaml").write_text("checks: []\n")
    init(repo)
    assert (repo / ".semipilot/config.yaml").read_text() == "checks: []\n"  # re-run is a no-op


def test_cli_init_and_status(tmp_path, capsys):
    repo = mkrepo(tmp_path, {"pyproject.toml": "[project]\nname='x'\n"})
    assert main(["--repo", str(repo), "init"]) == 0
    assert "detected: python" in capsys.readouterr().out
    assert main(["--repo", str(repo), "status"]) == 0
    assert "no features yet" in capsys.readouterr().out
    feat = repo / ".semipilot/features/hello"
    feat.mkdir(parents=True)
    (feat / "requirements.md").write_text("---\nstatus: draft\n---\n# R\n")
    main(["--repo", str(repo), "status"])
    assert "not approved" in capsys.readouterr().out
    (feat / "requirements.md").write_text("---\nstatus: approved\n---\n# S\n## Acceptance criteria\n- x [check: a]\n")
    main(["--repo", str(repo), "status"])
    assert "requirements approved" in capsys.readouterr().out
    assert main(["--repo", str(repo), "doctor", "--offline"]) in (0, 1)


def test_init_here_and_root_discovery_in_a_subfolder(tmp_path, capsys, monkeypatch):
    from semipilot.cli import find_repo
    repo = mkrepo(tmp_path, {"apps/web/index.js": "", "apps/api/package.json": json.dumps({"scripts": {"test": "vitest"}, "devDependencies": {"vitest": "1"}})})
    api = repo / "apps" / "api"
    # before init: the git root is the only root there is
    assert find_repo(api) == repo
    monkeypatch.chdir(api)
    assert main(["init", "--here"]) == 0
    out = capsys.readouterr().out
    assert "semipilot init → api" in out
    assert (api / ".semipilot" / "config.yaml").exists() and (api / ".github" / "agents" / "refiner.agent.md").exists()
    assert not (repo / ".semipilot").exists() and not (repo / ".github").exists()
    # after init: found from anywhere inside the project, and the git root is still not it
    (api / "src").mkdir()
    assert find_repo(api / "src") == api
    assert find_repo(repo / "apps" / "web") == repo
    monkeypatch.chdir(api / "src")
    assert main(["status"]) == 0
