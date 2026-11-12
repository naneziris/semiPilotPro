"""Chores: one small unattended fix per run, kept only when a purely mechanical gate passes (chore.py)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from semipilot import chore as chore_mod, cli
from semipilot.chore import Chore, ChoreError
from conftest import TEST_FILE_GOOD, step, write

ADD_TWO = "def add(a, b):\n    # FIXME: remove this comment\n    return a + b\n\n\ndef neg(a):\n    # FIXME: and this one\n    return -a\n"
ADD_ONE = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    # FIXME: and this one\n    return -a\n"
ADD_NONE = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    return -a\n"
MUL = "def mul(a, b):\n    # FIXME: third\n    return a * b\n"
CHORE = "PILOTINLOOP CHORE"


@pytest.fixture
def c(hc):
    """A project with a passing test, three FIXME findings in two files and a chore that finds them."""
    for path, text in (("calc/__init__.py", ""), ("calc/add.py", ADD_TWO), ("calc/mul.py", MUL),
                       ("tests/test_calc.py", TEST_FILE_GOOD)):
        (hc.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (hc.repo / path).write_text(text)
    hc.git("add", "-A")
    hc.git("commit", "-qm", "code with findings")
    hc.cfg["chores"]["items"] = [{"name": "fixme", "find": "grep -rn FIXME calc || true",
                                  "instruction": "Remove the FIXME comment by doing what it says."}]
    return hc


def scenario(h, *steps):
    h.scenario(extra={CHORE: list(steps)})


def run_chore(h, name=None, **kw):
    return h.do(lambda: Chore(h.repo, h.cfg, sleep_fn=h.sleeps.append, log_fn=lambda m: None).run(name, **kw))


def chore_calls(h):
    return [x for x in h.calls() if CHORE in x["prompt"]]


def branches(h):
    return h.git("branch", "--format=%(refname:short)").split()


# ---------------------------------------------------------------- the happy path
def test_one_finding_one_commit_one_branch_back_on_base(c):
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    entry = run_chore(c)
    assert entry["status"] == "fixed" and entry["target"] == "calc/add.py:2:    # FIXME: remove this comment"
    assert entry["left"] == 2 and entry["usage"]["calls"] == 1
    branch = entry["branch"]
    assert branch.startswith("chore/fixme-") and branch in branches(c)
    assert c.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main"          # tomorrow starts from the base again
    assert c.git("status", "--porcelain").strip() == ""
    assert "FIXME: remove" in (c.repo / "calc/add.py").read_text()               # main itself is untouched
    assert c.git("log", "-1", "--format=%s", branch).strip() == "chore(fixme): fix calc/add.py:2: # FIXME: remove this comment"
    assert c.git("diff", "--stat", "main", branch).count("|") == 1               # exactly one file
    prompt = chore_calls(c)[0]["prompt"]
    assert "calc/add.py:2:    # FIXME: remove this comment" in prompt and "Change at most 3 file(s)" in prompt
    assert "Remove the FIXME comment by doing what it says." in prompt
    assert "You are the" not in prompt                                           # no planner, no critics, no reviewer
    assert len(c.calls()) == 1


def test_runs_pick_up_where_the_last_one_stopped(c):
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    first = run_chore(c)
    c.git("merge", "-q", "--ff-only", first["branch"])                           # a human merged the small request
    scenario(c, step(actions=[write("calc/add.py", ADD_NONE)]))
    second = run_chore(c)
    assert second["status"] == "fixed" and second["target"].startswith("calc/add.py:6:")
    history = Chore(c.repo, c.cfg).load_state()["history"]
    assert [e["status"] for e in history] == ["fixed", "fixed"]
    assert not (c.repo / ".semipilot" / "chores").exists()                       # the memory is outside the repository


def test_a_fix_waiting_for_review_is_not_made_twice(c):
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    first = run_chore(c)                                                         # nobody merged it
    assert Chore(c.repo, c.cfg).listing() == [{"name": "fixme", "findings": 3, "skipped": 0, "waiting": 1}]
    scenario(c, step(actions=[write("calc/add.py", ADD_TWO.replace("    # FIXME: and this one\n", ""))]))
    second = run_chore(c)
    assert second["status"] == "fixed" and second["target"].startswith("calc/add.py:7:")   # the next finding
    assert second["branch"] != first["branch"]


def test_chores_stop_when_the_reviewer_is_behind(c):
    c.cfg["chores"]["max_open"] = 1
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    first = run_chore(c)
    n = len(c.calls())
    entry = run_chore(c)
    assert entry["status"] == "waiting_for_review" and first["branch"] in entry["detail"]
    assert len(c.calls()) == n                                                   # no agent call, no new branch
    c.git("merge", "-q", "--ff-only", first["branch"])                           # reviewed and merged
    scenario(c, step(actions=[write("calc/add.py", ADD_NONE)]))
    assert run_chore(c)["status"] == "fixed"


def test_nothing_to_do_costs_nothing(c):
    c.cfg["chores"]["items"][0]["find"] = "true"
    scenario(c)
    assert run_chore(c)["status"] == "nothing_to_do"
    assert c.calls() == [] and branches(c) == ["main"]


def test_dry_run_and_listing_change_nothing(c):
    scenario(c)
    entry = run_chore(c, dry_run=True)
    assert entry == {"status": "dry_run", "chore": "fixme", "target": "calc/add.py:2:    # FIXME: remove this comment", "findings": 3}
    assert Chore(c.repo, c.cfg).listing() == [{"name": "fixme", "findings": 3, "skipped": 0}]
    assert c.calls() == [] and branches(c) == ["main"]


# ---------------------------------------------------------------- the gate
def test_checks_failing_on_the_base_branch_means_no_attempt(c):
    (c.repo / "tests/test_calc.py").write_text(TEST_FILE_GOOD.replace("== 5", "== 6"))
    c.git("commit", "-qam", "a red base")
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    entry = run_chore(c)
    assert entry["status"] == "checks_fail_on_base" and c.calls() == [] and branches(c) == ["main"]


def test_a_fix_that_breaks_the_checks_is_thrown_away(c):
    broken = ADD_ONE.replace("return a + b", "return a - b")
    scenario(c, step(actions=[write("calc/add.py", broken)]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "test_add" in entry["detail"]
    assert len(chore_calls(c)) == 2                                              # one retry, with the errors
    assert "assert" in chore_calls(c)[1]["prompt"] and "still in the working tree" in chore_calls(c)[1]["prompt"]
    assert branches(c) == ["main"] and c.git("status", "--porcelain").strip() == ""
    assert (c.repo / "calc/add.py").read_text() == ADD_TWO


def test_second_attempt_can_fix_the_first(c):
    broken = ADD_ONE.replace("return a + b", "return a - b")
    scenario(c, step(actions=[write("calc/add.py", broken)]), step(actions=[write("calc/add.py", ADD_ONE)]))
    assert run_chore(c)["status"] == "fixed"


def test_existing_tests_are_locked(c):
    weakened = TEST_FILE_GOOD.replace("== 5", "== -1")
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE.replace("a + b", "a - b")), write("tests/test_calc.py", weakened)]))
    entry = run_chore(c)
    assert entry["status"] == "failed"
    assert "modified existing test files (tests/test_calc.py)" in chore_calls(c)[1]["prompt"]
    assert (c.repo / "tests/test_calc.py").read_text() == TEST_FILE_GOOD


def test_too_many_files_or_lines_is_not_a_chore(c):
    c.cfg["chores"]["max_files"] = 1
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE), write("calc/mul.py", "def mul(a, b):\n    return a * b\n")]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "the limit is 1" in entry["detail"]
    c.cfg["chores"]["max_files"], c.cfg["chores"]["max_diff_lines"] = 3, 1
    Chore(c.repo, c.cfg).reset_state()
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE + "\n\n# tidied\n# while\n# here\n")]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "the limit is 1" in entry["detail"]


def test_the_finding_must_actually_be_gone(c):
    scenario(c, step(actions=[write("calc/mul.py", MUL + "\n# unrelated\n")]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "still reported" in entry["detail"]


def test_hiding_a_finding_by_creating_another_does_not_pass(c):
    moved = ADD_ONE + "\n\ndef sub(a, b):\n    # FIXME: moved here\n    return a - b\n"
    scenario(c, step(actions=[write("calc/add.py", moved)]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "introduced a new one" in entry["detail"]   # 3 findings before, 3 after


def test_a_new_finding_elsewhere_does_not_pass(c):
    c.cfg["chores"]["items"][0]["find"] = "grep -rn 'FIXME\\|HACK' calc || true"
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE.replace("return a + b", "return a + b  # HACK"))]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "introduced a new one" in entry["detail"]


def test_instructions_and_cards_are_off_limits(c):
    (c.repo / "AGENTS.md").write_text("# rules\n")
    c.git("add", "-A")
    c.git("commit", "-qm", "instructions")
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE), write("AGENTS.md", "# rules\nFIXME comments are fine.\n")]),
             step(actions=[write("calc/add.py", ADD_ONE)]))
    entry = run_chore(c)
    assert entry["status"] == "fixed"
    assert "AGENTS.md, which a chore may not change" in chore_calls(c)[1]["prompt"]
    assert c.git("show", f"{entry['branch']}:AGENTS.md") == "# rules\n"


def test_blocked_means_not_a_small_fix_and_is_skipped_at_once(c):
    scenario(c, step(stdout="This needs a redesign.\nBLOCKED: removing it changes the public API"))
    entry = run_chore(c)
    assert entry["status"] == "blocked" and "public API" in entry["detail"] and branches(c) == ["main"]
    scenario(c, step(actions=[write("calc/add.py", ADD_TWO.replace("    # FIXME: and this one\n", ""))]))
    entry = run_chore(c)                                                         # the next run takes the next finding
    assert entry["status"] == "fixed" and entry["target"].startswith("calc/add.py:7:")


def test_a_finding_that_keeps_failing_is_skipped_until_reset(c):
    nothing = step(stdout="done")
    scenario(c, nothing)
    assert run_chore(c)["status"] == "failed" and run_chore(c)["status"] == "failed"
    assert Chore(c.repo, c.cfg).listing() == [{"name": "fixme", "findings": 3, "skipped": 1}]
    assert run_chore(c, dry_run=True)["target"].startswith("calc/add.py:7:")
    assert Chore(c.repo, c.cfg).reset_state("fixme") == 1
    assert run_chore(c, dry_run=True)["target"].startswith("calc/add.py:2:")


def test_an_agent_outage_keeps_the_finding_for_next_time(c):
    scenario(c, step(exit=1, stderr=c.err["quota"]))
    entry = run_chore(c)
    assert entry["status"] == "halted" and "quota_exhausted" in entry["detail"]
    assert branches(c) == ["main"] and Chore(c.repo, c.cfg).load_state()["failures"] == {}


def test_agent_switching_branches_is_undone(c):
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE), {"git": ["checkout", "-q", "-b", "sneaky"]}]))
    entry = run_chore(c)
    assert entry["status"] == "failed" and "switched the branch" in entry["detail"]
    assert c.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


# ---------------------------------------------------------------- configuration
def test_refuses_a_dirty_tree_and_missing_setup(c):
    (c.repo / "calc/scratch.py").write_text("x = 1\n")
    scenario(c)
    with pytest.raises(ChoreError) as e:
        run_chore(c)
    assert "dirty" in str(e.value)
    (c.repo / "calc/scratch.py").unlink()
    with pytest.raises(ChoreError) as e:
        run_chore(c, "nope")
    assert "no chore named 'nope'" in str(e.value)
    c.cfg["chores"]["items"] = []
    with pytest.raises(ChoreError) as e:
        run_chore(c)
    assert "no chores configured" in str(e.value)
    c.cfg["chores"]["items"] = [{"name": "Bad Name", "find": "true"}]
    with pytest.raises(ChoreError):
        run_chore(c)


def test_chore_can_be_gated_by_a_subset_of_checks(c):
    c.cfg["chores"]["items"][0]["checks"] = ["build"]
    (c.repo / "tests/test_calc.py").write_text(TEST_FILE_GOOD.replace("== 5", "== 6"))   # tests are red, build is fine
    c.git("commit", "-qam", "red tests")
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    assert run_chore(c)["status"] == "fixed"
    c.cfg["chores"]["items"][0]["checks"] = ["nope"]
    with pytest.raises(ChoreError):
        run_chore(c)


def test_match_filters_finder_output_and_instruction_only_chores_work(c):
    c.cfg["chores"]["items"] = [{"name": "fixme", "find": "echo 'Scanning...'; grep -rn FIXME calc; echo '3 problems'",
                                 "match": r"^[^:]+:\d+:"},
                                {"name": "tidy", "instruction": "Remove one needless comment."}]
    assert Chore(c.repo, c.cfg).listing() == [{"name": "fixme", "findings": 3, "skipped": 0},
                                               {"name": "tidy", "findings": None, "skipped": 0}]
    scenario(c, step(actions=[write("calc/mul.py", "def mul(a, b):\n    return a * b\n")]))
    entry = run_chore(c, "tidy")
    assert entry["status"] == "fixed" and entry.get("target") is None
    assert c.git("log", "-1", "--format=%s", entry["branch"]).strip() == "chore(tidy): one tidy fix in calc/mul.py"
    assert "no finder: find ONE instance" in chore_calls(c)[0]["prompt"]


def test_signature_survives_moving_lines():
    a = chore_mod.signature("src/a.ts:12:5: 'x' is defined but never used  no-unused-vars")
    b = chore_mod.signature("src/a.ts:40:9: 'x' is defined but never used  no-unused-vars")
    assert a == b and a != chore_mod.signature("src/b.ts:12:5: 'x' is defined but never used  no-unused-vars")


# ---------------------------------------------------------------- one small request per chore
def test_open_mr_pushes_only_the_chore_branch(c, monkeypatch, tmp_path):
    fake = str(Path(__file__).resolve().parent / "fake_forge.py")
    log = tmp_path / "forge.jsonl"
    monkeypatch.setenv("FAKE_FORGE_LOG", str(log))
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    c.git("remote", "add", "origin", str(bare))
    c.git("push", "-q", "origin", "main")
    c.cfg["forge"].update({"provider": "github", "commands": {
        "mr_create": [sys.executable, fake, "pr", "create", "--title", "{title}", "--body-file", "{body_file}",
                      "--base", "{base}", "--head", "{branch}"]}})
    c.cfg["chores"]["open_mr"] = True
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    entry = run_chore(c)
    assert entry["status"] == "fixed" and entry["mr"].endswith("/merge_requests/7")
    create = json.loads(log.read_text().splitlines()[-1])
    assert create[create.index("--base") + 1] == "main" and create[create.index("--head") + 1] == entry["branch"]
    body = Path(create[create.index("--body-file") + 1]).read_text()
    assert "Finding: `calc/add.py:2:" in body and "no existing test changed; the finding is gone" in body
    remote = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=bare, capture_output=True, text=True).stdout.split()
    assert sorted(remote) == sorted(["main", entry["branch"]])


# ---------------------------------------------------------------- the command line
def test_cli_chore(c, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda repo, path=None: c.cfg)
    run = lambda *a: c.do(lambda: cli.main(["--repo", str(c.repo), "chore", *a]))
    scenario(c, step(actions=[write("calc/add.py", ADD_ONE)]))
    assert run("--list") == 0
    assert "fixme" in capsys.readouterr().out and c.calls() == []
    assert run("--dry-run") == 0
    assert run() == 0
    out = capsys.readouterr().out
    assert "fixme: fixed — calc/add.py:2:" in out and "Next: read `git show" in out
    assert run("--history") == 0
    assert "fixme: fixed" in capsys.readouterr().out
    scenario(c, step(stdout="nothing"))
    assert run() == 2                                                            # did not pass its gate
    assert "nothing kept" in capsys.readouterr().out
    assert run("--reset") == 0
    c.cfg["chores"]["items"] = []
    assert run() == 1
