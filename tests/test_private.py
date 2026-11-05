"""`private: true` and `git.local_paths`: trial semipilot in a team repository with uncommitted local changes."""
import pytest

from conftest import ADD_BAD, ADD_OK, Harness, step, write
from semipilot.config import EXCLUDE_BEGIN, local_set, sync_excludes
from semipilot.initcmd import set_private
from semipilot.orchestrator import PreflightError, validate_plan
from conftest import PLAN

TEAM_AGENT = "# team agent\n"
MY_AGENT = "# team agent\n\nmy local tweak\n"
PKG_TEAM = '{"name": "x", "scripts": {}}\n'
PKG_MINE = '{"name": "x", "scripts": {"semipilot": "semipilot run"}}\n'


def with_local_changes(tmp_path, harness="copilot"):
    hs = Harness(tmp_path, harness=harness)
    (hs.repo / ".github" / "agents").mkdir(parents=True)
    (hs.repo / ".github" / "agents" / "reviewer.md").write_text(TEAM_AGENT)
    (hs.repo / "package.json").write_text(PKG_TEAM)
    hs.git("add", "-A")
    hs.git("commit", "-qm", "team files")
    # my uncommitted trial changes: a modified tracked agent, a new agent, a modified package.json
    (hs.repo / ".github" / "agents" / "reviewer.md").write_text(MY_AGENT)
    (hs.repo / ".github" / "agents" / "mine.md").write_text("# my new agent\n")
    (hs.repo / "package.json").write_text(PKG_MINE)
    hs.cfg["git"]["local_paths"] = [".github/", "package.json"]
    return hs


def committed_on_run_branch(hs):
    return [f for f in hs.git("log", "--name-only", "--format=", "main..feat/calc").splitlines() if f.strip()]


def assert_local_intact(hs):
    assert (hs.repo / ".github" / "agents" / "reviewer.md").read_text() == MY_AGENT
    assert (hs.repo / ".github" / "agents" / "mine.md").read_text() == "# my new agent\n"
    assert (hs.repo / "package.json").read_text() == PKG_MINE


@pytest.mark.parametrize("harness", ["copilot", "claude"])
def test_local_changes_do_not_block_a_run_and_are_never_committed(tmp_path, harness):
    hs = with_local_changes(tmp_path, harness)
    hs.scenario()
    o, reason = hs.run()
    assert reason == "completed"
    files = committed_on_run_branch(hs)
    assert "calc/add.py" in files
    assert not any(f.startswith(".github/") or f == "package.json" for f in files)
    assert_local_intact(hs)


def test_without_local_paths_the_same_changes_still_block(tmp_path):
    hs = with_local_changes(tmp_path)
    hs.cfg["git"]["local_paths"] = []
    hs.scenario()
    with pytest.raises(PreflightError, match="dirty"):
        hs.run()


def test_resets_after_a_failed_attempt_keep_local_changes(tmp_path):
    hs = with_local_changes(tmp_path)
    hs.scenario(implementer_t1=[step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)]),
                                step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = hs.run()
    assert reason == "completed" and hs.task("T1")["attempts"] == 2
    assert_local_intact(hs)


def test_an_agent_edit_to_a_local_file_is_reverted_and_retried(tmp_path):
    hs = with_local_changes(tmp_path)
    hs.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK), write("package.json", "{}\n")]),
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = hs.run()
    assert reason == "completed" and hs.task("T1")["attempts"] == 2
    assert_local_intact(hs)
    assert any("changed local file(s), restored: package.json" in w for w in hs.progress()["warnings"])
    assert "package.json" not in committed_on_run_branch(hs)


def test_a_plan_that_needs_a_local_file_is_rejected(tmp_path):
    hs = with_local_changes(tmp_path)
    plan = {**PLAN, "tasks": [dict(PLAN["tasks"][0], expected_files=["calc/add.py", "package.json"]), PLAN["tasks"][1]]}
    errors = validate_plan(plan, hs.cfg, None, local_set(hs.repo, hs.cfg))
    assert any("package.json" in e and "keeps local" in e for e in errors)


def test_the_prompts_tell_agents_which_files_are_local(tmp_path):
    hs = with_local_changes(tmp_path)
    hs.scenario()
    hs.run()
    planner = [c for c in hs.calls() if "Output **only** a JSON object" in c["prompt"]][0]["prompt"]
    assert "`.github/`" in planner and "`package.json`" in planner and "BLOCKED" in planner


# ------------------------------------------------------------------ private: true
def private_harness(tmp_path, harness="copilot"):
    hs = Harness(tmp_path, harness=harness)
    hs.git("rm", "-rq", "--cached", ".semipilot")  # a team repository that never had semipilot committed
    hs.git("commit", "-qm", "team repo")
    hs.cfg["private"] = True
    return hs


@pytest.mark.parametrize("harness", ["copilot", "claude"])
def test_private_run_commits_only_the_features_code(tmp_path, harness):
    hs = private_harness(tmp_path, harness)
    main_before = hs.git("rev-parse", "main")
    hs.scenario()
    o, reason = hs.run()
    assert reason == "completed"
    files = committed_on_run_branch(hs)
    assert files and not any(f.startswith(".semipilot/") for f in files)
    assert hs.git("rev-parse", "main") == main_before  # nothing auto-committed onto the base branch
    assert hs.git("status", "--porcelain").strip() == ""  # semipilot's files are ignored locally
    assert (hs.feat / "report.md").exists() and (hs.feat / "implementation-progress.json").exists()


def test_private_resume_from_main_uses_the_local_checkpoint(tmp_path):
    hs = private_harness(tmp_path)
    hs.scenario(implementer_t1=[step(exit=1, stderr=hs.err["fatal"])])
    o, reason = hs.run()
    assert reason == "auth_failure"
    hs.git("checkout", "-q", "main")
    with pytest.raises(PreflightError, match="semipilot resume calc"):
        hs.run()
    hs.scenario()
    o, reason = hs.resume()
    assert reason == "completed"
    assert not any(f.startswith(".semipilot/") for f in committed_on_run_branch(hs))


def test_exclude_block_is_idempotent_and_removed_when_off(tmp_path):
    hs = private_harness(tmp_path)
    hs.cfg["git"]["local_paths"] = [".github/"]
    path = sync_excludes(hs.repo, hs.cfg)
    sync_excludes(hs.repo, hs.cfg)
    text = path.read_text()
    assert text.count(EXCLUDE_BEGIN) == 1 and "/.semipilot/" in text and "/.github/" in text
    hs.cfg["private"], hs.cfg["git"]["local_paths"] = False, []
    sync_excludes(hs.repo, hs.cfg)
    assert EXCLUDE_BEGIN not in path.read_text()


def test_exclude_patterns_are_anchored_at_the_project_in_a_monorepo(h_sub):
    h_sub.cfg["private"] = True
    text = sync_excludes(h_sub.repo, h_sub.cfg).read_text()
    assert "/apps/api/.semipilot/" in text


def test_set_private_edits_only_its_lines(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("harness: copilot\n\nchecks:\n  - name: t\n    cmd: pytest\n")
    assert set_private(cfg)
    text = cfg.read_text()
    assert "private: true" in text and 'local_paths:\n    - ".github/"' in text and "cmd: pytest" in text
    assert not set_private(cfg)  # idempotent
    import yaml
    data = yaml.safe_load(text)
    assert data["private"] is True and data["git"]["local_paths"] == [".github/"]
