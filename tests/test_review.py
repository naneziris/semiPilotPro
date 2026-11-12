"""The review gate: the red check, the reviewer agent and the review packet that opens the report."""
import json

import pytest

from semipilot import cli, review
from conftest import REVIEW_OK, TEST_FILE_GOOD, TEST_FILE_MUL, step, task_of, write

VACUOUS = "def test_add():\n    assert True\n"          # passes with no implementation: proves nothing


# ---------------------------------------------------------------- red before green
def test_red_check_records_that_locked_tests_fail_first(h):
    h.scenario()
    _, reason = h.run()
    assert reason == "completed"
    assert h.progress()["red_check"] == {"T1": "red", "T2": "red"}
    rep = h.report()
    assert "| Red first |" in rep and "| yes |" in rep
    assert "already pass" not in rep


def test_a_test_that_passes_before_the_code_exists_is_flagged(h):
    h.scenario(test_writer=[step(actions=[write("tests/test_calc.py", VACUOUS), write("tests/test_mul.py", TEST_FILE_MUL)])])
    _, reason = h.run()
    assert reason == "completed"                              # warn is the default: the run goes on
    p = h.progress()
    assert p["red_check"] == {"T1": "green", "T2": "red"}
    assert any("T1: its locked tests (tests/test_calc.py) already pass" in w for w in p["warnings"])
    rep = h.report()
    assert "tests of T1 passed before the code existed" in rep   # in "Needs attention"
    assert "| **no** |" in rep


def test_red_check_halt_mode_stops_before_any_code(hc):
    hc.cfg["tests"]["red_check"] = "halt"
    hc.scenario(test_writer=[step(actions=[write("tests/test_calc.py", VACUOUS), write("tests/test_mul.py", TEST_FILE_MUL)])])
    _, reason = hc.run()
    assert reason == "tests_not_red"
    assert not any("Implement **only task" in c["prompt"] for c in hc.calls())
    _, reason = hc.resume()                                    # a human read them and decided to go on
    assert reason == "completed"


def test_red_check_off_and_without_a_scoped_test_check(hc):
    hc.cfg["tests"]["red_check"] = "off"
    hc.scenario()
    hc.run()
    assert hc.progress()["red_check"] == {}


def test_red_check_is_skipped_when_no_check_uses_task_tests(hc):
    hc.cfg["checks"][1]["cmd"] = hc.cfg["checks"][1]["cmd"].replace("{task_tests}", "")
    hc.scenario()
    hc.run()   # (every task then runs the whole suite, so T1 cannot pass here — only the red check matters)
    assert hc.progress()["red_check"] == {"T1": "skipped", "T2": "skipped"}


def test_an_acceptance_ref_no_locked_test_names_is_flagged(hc):
    renamed = TEST_FILE_MUL.replace("test_mul", "test_times")   # the criterion says [check: test_mul]
    hc.scenario(test_writer=[step(actions=[write("tests/test_calc.py", TEST_FILE_GOOD), write("tests/test_times.py", renamed)])])
    hc.run()
    assert any("no locked test names the acceptance ref(s) test_mul" in w for w in hc.progress()["warnings"])
    assert "**none found**" in hc.report()


# ---------------------------------------------------------------- the reviewer agent
def test_reviewer_runs_once_after_the_last_task_and_opens_the_report(h):
    h.scenario()
    _, reason = h.run()
    assert reason == "completed"
    rv = h.progress()["review"]
    assert rv["verdict"] == "ship" and rv["head"]
    calls = [c for c in h.calls() if "You are the reviewer" in task_of(c["prompt"])]
    assert len(calls) == 1
    prompt = calls[0]["prompt"]
    p = h.progress()
    assert f"git diff {p['base_commit'][:12]}.." in prompt and "':(exclude).semipilot'" in prompt
    assert "T1 add function — commit" in prompt and "spec_fidelity" in prompt   # tasks + the rubric (its role)
    rep = h.report()
    assert rep.index("## 0. Review packet") < rep.index("## 1. Assumptions")
    assert "Reviewer agent: **ship**" in rep and "### Read first" in rep
    assert "calc/add.py — the only logic" in rep                # the reviewer's read-first list
    assert "### Evidence per acceptance criterion" in rep and "`tests/test_calc.py`" in rep
    assert "### Where the change is" in rep and "| `calc/add.py` | +2/-0 | T1 |" in rep
    assert "### Reading order" in rep and f"git show {h.task('T1')['commit'][:8]}" in rep
    assert "it points, it does not decide" in rep


def test_reviewer_is_read_only_whatever_it_tries(h):
    h.scenario(reviewer=[step(stdout=json.dumps(REVIEW_OK), actions=[write("calc/add.py", "def add(a, b):\n    return 0\n"),
                                                                    write("notes.txt", "reviewed")])])
    _, reason = h.run()
    assert reason == "completed"
    assert "a + b" in (h.repo / "calc/add.py").read_text() and not (h.repo / "notes.txt").exists()
    assert h.git("status", "--porcelain").strip() == ""


def test_a_blocker_forces_needs_changes_but_never_fails_the_run(h):
    verdict = {"verdict": "ship", "summary": "Looks fine.",
               "rubric": [{"id": "spec_fidelity", "score": "pass", "evidence": "calc/add.py:1"},
                          {"id": "test_honesty", "score": "weird", "evidence": ""}],
               "findings": [{"severity": "minor", "file": "calc/mul.py", "line": 1, "note": "name is terse"},
                            {"severity": "blocker", "file": "calc/add.py", "line": 2, "task": "T1",
                             "note": "returns the wrong value for negative numbers", "suggestion": "handle the sign"},
                            {"severity": "???", "file": "x", "note": ""}],
               "read_first": ["calc/add.py:2 — the arithmetic"]}
    h.scenario(reviewer=[step(stdout="Here is my review:\n```json\n" + json.dumps(verdict) + "\n```")])
    _, reason = h.run()
    assert reason == "completed"                                # advice, not a gate
    rv = h.progress()["review"]
    assert rv["verdict"] == "needs_changes"                     # a blocker is never "ship"
    assert [f["severity"] for f in rv["findings"]] == ["blocker", "minor"]   # sorted, the empty one dropped
    assert rv["rubric"][1]["score"] == "concern"                # an unknown score is not a pass
    rep = h.report()
    assert "Needs attention: 1 blocker(s) from the reviewer" in rep
    assert "**blocker** calc/add.py:2 — returns the wrong value" in rep
    assert "→ handle the sign" in rep


def test_reviewer_without_a_verdict_is_a_note_not_a_failure(hc):
    hc.scenario(reviewer=[step(stdout="I could not decide.")])
    _, reason = hc.run()
    assert reason == "completed"
    assert hc.progress()["review"]["verdict"] == "no_verdict"
    assert "Reviewer agent: **no verdict**" in hc.report()


def test_reviewer_outage_does_not_undo_a_finished_run(h):
    h.scenario(reviewer=[step(exit=1, stderr=h.err["quota"])])
    _, reason = h.run()
    assert reason == "completed"
    p = h.progress()
    assert p["review"]["verdict"] == "not_run" and [t["status"] for t in p["tasks"]] == ["done", "done"]
    assert any("semipilot review calc --agent" in w for w in p["warnings"])
    # later, when the quota is back
    h.scenario()
    h.do(lambda: h.loop().review_again())
    assert h.progress()["review"]["verdict"] == "ship"
    assert "Reviewer agent: **ship**" in h.report()


def test_review_agent_can_be_switched_off(hc):
    hc.cfg["review"]["agent"] = False
    hc.scenario()
    _, reason = hc.run()
    assert reason == "completed"
    assert not any("You are the reviewer" in task_of(c["prompt"]) for c in hc.calls())
    rep = hc.report()
    assert "## 0. Review packet" in rep and "Reviewer agent" not in rep     # the packet is built from facts anyway


def test_reviewer_role_can_be_overridden_per_project(hc):
    roles = hc.repo / ".semipilot" / "roles"
    roles.mkdir()
    (roles / "reviewer.md").write_text("You are OUR reviewer. House rubric: no singletons.\n")
    hc.git("add", "-A")
    hc.git("commit", "-qm", "house rubric")
    hc.scenario()
    hc.run()
    prompt = next(c["prompt"] for c in hc.calls() if "You are the reviewer" in task_of(c["prompt"]))
    assert prompt.startswith("You are OUR reviewer.") and "no singletons" in prompt


def test_blocked_run_still_gets_a_packet_and_a_review_of_what_was_built(hc):
    bad = step(actions=[write("calc/mul.py", "def mul(a, b):\n    return a + b\n")])
    hc.scenario(implementer_t2=[bad, bad, bad])
    _, reason = hc.run()
    assert reason == "completed_with_blocked"
    rep = hc.report()
    assert "Needs attention: blocked: T2" in rep
    assert hc.progress()["review"]["verdict"] == "ship"         # T1 was built and is worth reading


def test_cli_review_agent_flag(hc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda repo, path=None: hc.cfg)
    hc.cfg["review"]["agent"] = False
    hc.scenario()
    hc.run()
    hc.cfg["review"]["agent"] = True
    assert hc.do(lambda: cli.main(["--repo", str(hc.repo), "review", "calc", "--agent"])) == 0
    assert "Reviewer agent: **ship**" in capsys.readouterr().out
    assert hc.git("status", "--porcelain").strip() == ""        # the new report is committed with the run state


# ---------------------------------------------------------------- shaping the reviewer's answer
def test_normalize_caps_and_cleans():
    raw = {"verdict": "SHIP", "summary": "ok\nfine", "findings": [{"severity": "major", "note": f"n{i}", "file": "f"} for i in range(30)],
           "read_first": ["a", "", None, "b"], "rubric": "nonsense"}
    out = review.normalize(raw, max_findings=5)
    assert out["verdict"] == "ship" and out["summary"] == "ok fine"
    assert len(out["findings"]) == 5 and out["read_first"] == ["a", "b"] and out["rubric"] == []
    assert review.normalize(None, 5)["verdict"] == "no_verdict"
    assert review.normalize({"verdict": "ship", "rubric": [{"id": "x", "score": "fail"}]}, 5)["verdict"] == "needs_changes"
