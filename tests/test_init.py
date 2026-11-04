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


SKILL_NAMES = ["semipilot-knowledge", "semipilot-refine", "semipilot-run", "semipilot-scribe", "semipilot-spec-critic"]


def test_init_writes_only_what_is_needed_and_never_overwrites(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": "[project]\nname='x'\n", ".github/copilot-instructions.md": "# mine\n"})
    d, report, info = init(repo, harness="copilot")
    written = sorted(str(p.relative_to(repo)) for a, p in report if a == "write")
    assert written == sorted([".semipilot/config.yaml", ".semipilot/.gitignore"] + [f".agents/skills/{n}" for n in SKILL_NAMES])
    assert info["harness"] == "copilot" and info["instructions"] == ".github/copilot-instructions.md"
    assert (repo / ".github/copilot-instructions.md").read_text() == "# mine\n"  # yours, untouched
    assert not (repo / "AGENTS.md").exists()  # an instructions file already exists
    assert not (repo / ".github/agents").exists() and not (repo / ".github/prompts").exists()  # v0.1 files are gone
    assert "harness: copilot" in (repo / ".semipilot/config.yaml").read_text()
    assert (repo / ".agents/skills/semipilot-knowledge/scripts/kb.py").exists()
    (repo / ".semipilot/config.yaml").write_text("checks: []\n")
    init(repo)
    assert (repo / ".semipilot/config.yaml").read_text() == "checks: []\n"  # re-run is a no-op


def test_init_for_claude_code(tmp_path):
    repo = mkrepo(tmp_path, {"package.json": json.dumps({"scripts": {"test": "jest", "build": "tsc"}, "devDependencies": {"jest": "29"}})})
    d, report, info = init(repo, harness="claude-code")
    assert info["harness"] == "claude"
    assert all((repo / ".claude/skills" / n / "SKILL.md").exists() for n in SKILL_NAMES)
    assert not (repo / ".agents").exists()
    agents = (repo / "AGENTS.md").read_text()  # no instructions file yet → AGENTS.md, read by Claude Code and Copilot
    assert "npx jest" in agents and "{{TODO" in agents and "{{BUILD}}" not in agents
    assert not (repo / "CLAUDE.md").exists()  # Claude Code reads AGENTS.md when there is no CLAUDE.md


def test_init_claude_with_only_copilot_instructions_gets_a_claude_md_pointer(tmp_path):
    repo = mkrepo(tmp_path, {".github/copilot-instructions.md": "# ours\n"})
    init(repo, harness="claude")
    assert (repo / "CLAUDE.md").read_text().strip() == "@.github/copilot-instructions.md"


def test_init_skills_for_both_chats_and_switching_harness(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": ""})
    d, report, info = init(repo, harness="copilot", skills_for=["copilot", "claude"])
    assert (repo / ".agents/skills/semipilot-refine/SKILL.md").exists() and (repo / ".claude/skills/semipilot-refine/SKILL.md").exists()
    assert any("twice" in n for n in info["notes"])
    d, report, info = init(repo, harness="claude")  # existing config: only the harness line changes
    assert "harness: claude" in (repo / ".semipilot/config.yaml").read_text()
    assert ("update", repo / ".semipilot/config.yaml") in report


def test_init_notes_legacy_v01_files(tmp_path):
    repo = mkrepo(tmp_path, {".github/agents/pilotinloop-planner.agent.md": "x", ".github/prompts/refine-requirements.prompt.md": "x"})
    d, report, info = init(repo, harness="copilot")
    assert any("pilotinloop-planner.agent.md is no longer used" in n for n in info["notes"])
    assert (repo / ".github/agents/pilotinloop-planner.agent.md").exists()  # noted, never deleted


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
    assert (api / ".semipilot" / "config.yaml").exists()
    assert any((api / d / "semipilot-refine" / "SKILL.md").exists() for d in (".agents/skills", ".claude/skills"))
    assert not (repo / ".semipilot").exists() and not (repo / ".agents").exists() and not (repo / ".claude").exists()
    # after init: found from anywhere inside the project, and the git root is still not it
    (api / "src").mkdir()
    assert find_repo(api / "src") == api
    assert find_repo(repo / "apps" / "web") == repo
    monkeypatch.chdir(api / "src")
    assert main(["status"]) == 0


def test_rerun_refreshes_skills_from_another_version_but_never_the_config(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": ""})
    init(repo, harness="claude")
    skill = repo / ".claude/skills/semipilot-refine/SKILL.md"
    skill.write_text(skill.read_text().replace('version: "0.2.2"', 'version: "0.1.9"'))
    (repo / ".semipilot/config.yaml").write_text("harness: claude\nchecks: [{name: t, cmd: x}]\n")
    d, report, info = init(repo, force=True)
    assert ("update", repo / ".claude/skills/semipilot-refine") in report
    assert 'version: "0.2.2"' in skill.read_text()
    assert (repo / ".semipilot/config.yaml").read_text() == "harness: claude\nchecks: [{name: t, cmd: x}]\n"
    d, report, info = init(repo)
    assert ("skip", repo / ".claude/skills/semipilot-refine") in report  # current version: kept


def test_init_never_downgrades_newer_skills(tmp_path):
    repo = mkrepo(tmp_path, {"pyproject.toml": ""})
    init(repo, harness="claude")
    skill = repo / ".claude/skills/semipilot-run/SKILL.md"
    skill.write_text(skill.read_text().replace('version: "0.2.2"', 'version: "0.3.0"'))
    d, report, info = init(repo)
    assert ("skip", repo / ".claude/skills/semipilot-run") in report and 'version: "0.3.0"' in skill.read_text()
