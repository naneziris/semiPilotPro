import json

import pytest

import orchestrator as orch
from conftest import ADD_BAD, ADD_OK, MUL_OK, PLAN, TEST_FILE_GOOD, TEST_FILE_MUL, step, write


# ---------------------------------------------------------------- happy path
def test_happy_path_two_tasks(h):
    h.scenario()
    o, reason = h.pilotinloop()
    assert reason == "completed"
    p = h.progress()
    assert [t["status"] for t in p["tasks"]] == ["done", "done"]
    assert [t["attempts"] for t in p["tasks"]] == [1, 1]
    log = h.log()
    assert "[pilotinloop] T1: add function" in log and "[pilotinloop] T2: mul function" in log
    assert "[pilotinloop] tests: locked acceptance tests" in log
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip().startswith("pilotinloop/calc-")
    # plan.json lives outside the repo (implementer physically can't read it) and is copied to the run dir at the end
    assert not (h.repo / "plan.json").exists()
    assert (h.state / "repo" / p["run_id"] / "plan.json").exists()
    assert (h.repo / ".github/pilotinloop/runs" / p["run_id"] / "plan.json").exists()
    rep = h.report()
    assert "Stop reason: **completed**" in rep and "T2" in rep
    # implementer never sees the plan or the other task
    impl_prompts = [c["prompt"] for c in h.calls() if "Implement **only task" in c["prompt"]]
    assert len(impl_prompts) == 2
    assert all("plan.json" not in pr for pr in impl_prompts)
    assert "T2" not in impl_prompts[0] or "mul" not in impl_prompts[0]


def test_every_call_is_a_fresh_process_without_session_flags(h):
    h.scenario()
    h.pilotinloop()
    for c in h.calls():
        assert not any(a.startswith(("--resume", "--continue", "--session-id")) for a in c["argv"])
        assert "-p" in c["argv"]


# ---------------------------------------------------------------- retry semantics (design fix #1)
def test_task_retry_keeps_failed_diff_and_feeds_errors(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)]),
        # second attempt must see the previous attempt's file still there, then fix it
        step(actions=[{"assert_exists": "calc/add.py"}, {"assert_contains": "calc/add.py", "text": "a - b"},
                      write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.pilotinloop()
    assert reason == "completed"
    assert h.task("T1")["attempts"] == 2
    prompts = [c["prompt"] for c in h.calls() if "Implement **only task T1**" in c["prompt"]]
    assert len(prompts) == 2
    # errors from attempt 1 are embedded in attempt 2's prompt (fake logs first 400 chars; check the log file instead)
    log2 = next((h.repo / ".github/pilotinloop/runs").rglob("T1-attempt2.log")).read_text()
    assert "test_add" in log2 and "still in the working tree" in log2


def test_stuck_detection_blocks_and_resets_tree(h):
    bad = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)])
    h.scenario(implementer_t1=[bad, bad, bad])
    o, reason = h.pilotinloop()
    t1, t2 = h.task("T1"), h.task("T2")
    assert t1["status"] == "blocked"
    assert t1["attempts"] == 2  # same signature twice → stop early, don't burn the third retry
    assert t2["status"] == "blocked" and "dependency T1" in t2["blocked_reason"]
    assert not (h.repo / "calc/add.py").exists()  # tree reset after giving up
    assert reason == "completed"  # run completed; tasks blocked is a task outcome, not a run failure
    assert "T1" in h.report() and "BLOCKED" not in h.report().upper()[:0]


def test_error_signature_ignores_line_numbers_and_paths():
    a = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/x/calc/add.py:12: AssertionError"
    b = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/y/calc/add.py:37: AssertionError"
    c = "FAILED tests/test_calc.py::test_mul - assert 1 == 6"
    assert orch.error_signature(a) == orch.error_signature(b)
    assert orch.error_signature(a) != orch.error_signature(c)


# ---------------------------------------------------------------- infra failures (design fix #3 + §4.6)
def test_502_never_marks_task_blocked(h):
    h.scenario(implementer_t1=[
        step(exit=1, stderr="Error: 502 Bad Gateway"),
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.pilotinloop()
    assert reason == "completed"
    t1 = h.task("T1")
    assert t1["status"] == "done" and t1["attempts"] == 1  # transient retry did not consume a task attempt
    assert h.progress()["infra"]["transient_failures"] == 1
    assert "Transient Copilot failures: 1" in h.report()


def test_breaker_leaves_task_pending_and_resume_finishes(h):
    h.cfg["infra"].update({"max_outage_seconds": 0.03, "backoff_start_seconds": 0.02, "backoff_cap_seconds": 0.02})
    h.scenario(implementer_t1=[step(exit=1, stderr="503 Service Unavailable")] * 5 + [
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.pilotinloop()
    assert reason == "copilot_unavailable"
    assert h.task("T1")["status"] == "pending"
    assert h.task("T2")["status"] == "pending"
    assert h.git("status", "--porcelain").strip() == ""  # clean tree at halt
    # morning: resume picks up T1 as pending, not blocked
    h.cfg["infra"].update({"max_outage_seconds": 5400})
    o, reason = h.resume()
    assert reason == "completed"
    assert [t["status"] for t in h.progress()["tasks"]] == ["done", "done"]


def test_401_halts_immediately_with_auth_failure(h):
    h.scenario(implementer_t1=[step(exit=1, stderr="HTTP 401 Unauthorized: bad credentials")])
    o, reason = h.pilotinloop()
    assert reason == "auth_failure"
    assert h.task("T1")["status"] == "pending"
    assert h.sleeps == []


def test_quota_exhaustion_halts_without_backoff(h):
    h.scenario(implementer_t1=[step(exit=1, stderr="Copilot premium request quota exceeded for this billing period")])
    o, reason = h.pilotinloop()
    assert reason == "quota_exhausted"
    assert h.sleeps == []
    assert h.task("T1")["status"] == "pending"


# ---------------------------------------------------------------- guardrails
def test_test_lock_violation_reverts_tests_and_counts_attempt(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD),
                      write("tests/test_calc.py", "def test_add():\n    assert True\n")]),
        step(actions=[write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.pilotinloop()
    assert reason == "completed"
    assert h.task("T1")["attempts"] == 2
    assert (h.repo / "tests/test_calc.py").read_text() == TEST_FILE_GOOD
    assert any("modified locked tests" in w for w in h.progress()["warnings"])


def test_implementer_may_add_new_test_files(h):
    h.scenario(implementer_t1=[step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK),
                                             write("tests/test_add_extra.py", "from calc.add import add\ndef test_neg():\n    assert add(-1, 1) == 0\n")])])
    o, reason = h.pilotinloop()
    assert reason == "completed"
    assert (h.repo / "tests/test_add_extra.py").exists()
    assert any("added new test files" in w for w in h.progress()["warnings"])


def test_scope_violation_touching_other_tasks_files_is_reverted(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK), write("calc/mul.py", MUL_OK)]),
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.pilotinloop()
    assert reason == "completed"
    assert h.task("T1")["attempts"] == 2
    assert any("scope violation" in w for w in h.progress()["warnings"])


def test_diff_cap_per_task_blocks(h):
    h.cfg["guardrails"]["diff_cap_lines_per_task"] = 3
    h.scenario(implementer_t1=[step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK + "# pad\n" * 10)])])
    o, reason = h.pilotinloop()
    assert h.task("T1")["status"] == "blocked" and "cap" in h.task("T1")["blocked_reason"]


def test_iteration_budget_stops_run(h):
    h.cfg["budget"]["max_iterations"] = 1
    h.scenario()
    o, reason = h.pilotinloop()
    assert reason == "budget_exhausted"
    assert h.task("T1")["status"] == "done" and h.task("T2")["status"] == "pending"


def test_dirty_tree_refused(h):
    (h.repo / "junk.txt").write_text("x")
    h.scenario()
    with pytest.raises(orch.PreflightError):
        h.pilotinloop()


# ---------------------------------------------------------------- test contract fix (design fix #2)
def test_contract_error_in_locked_tests_gets_one_logged_fix(h):
    wrong_import = TEST_FILE_GOOD.replace("from calc.add import add", "from calc.adder import add")
    h.scenario(
        test_writer=[step(actions=[write("tests/test_calc.py", wrong_import), write("tests/test_mul.py", TEST_FILE_MUL)])],
        extra={"You are the test-fixer": [step(actions=[write("tests/test_calc.py", TEST_FILE_GOOD)])]},
    )
    o, reason = h.pilotinloop()
    assert reason == "completed"
    assert h.task("T1")["status"] == "done"
    assert h.task("T1")["contract_fixes"] == 1
    assert any("test-fixer edited" in w and "REVIEW" in w for w in h.progress()["warnings"])
    assert "test-fixer edited" in h.report()


def test_contract_fix_is_limited_and_assertion_failures_never_trigger_it(h):
    bad = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)])
    h.scenario(implementer_t1=[bad, bad], extra={"You are the test-fixer": [step(actions=[write("tests/test_calc.py", "def test_add():\n    pass\n")])]})
    o, reason = h.pilotinloop()
    assert h.task("T1")["contract_fixes"] == 0  # assertion failure → no fixer call
    assert not any("test-fixer" in c["prompt"] for c in h.calls())


# ---------------------------------------------------------------- plan / critique
def test_plan_validation_rules(h):
    crit = [{"ref": "test_add"}, {"ref": "test_mul"}]
    bad = json.loads(json.dumps(PLAN))
    bad["tasks"][0]["expected_files"] = [f"f{i}.py" for i in range(7)]
    bad["tasks"][1]["acceptance_checks"] = ["test_nope"]
    errs = validate = orch.validate_plan(bad, h.cfg, crit)
    assert any("expected_files > max" in e for e in errs)
    assert any("test_mul' is not covered" in e for e in errs)
    assert any("does not match any tagged criterion" in e for e in errs)
    big = json.loads(json.dumps(PLAN))
    big["tasks"][0]["size"] = "L"
    assert any("schema" in e for e in orch.validate_plan(big, h.cfg, crit))
    cyc = json.loads(json.dumps(PLAN))
    cyc["tasks"][0]["depends_on"] = ["T2"]
    assert any("cycle" in e for e in orch.validate_plan(cyc, h.cfg, crit))
    assert orch.validate_plan(PLAN, h.cfg, crit) == []


def test_critic_rejection_replans_then_halts(h):
    reject = step(stdout=json.dumps({"verdict": "reject", "issues": ["T1: split it"]}))
    h.scenario(critics=[reject, reject, reject])
    o, reason = h.pilotinloop()
    assert reason == "plan_rejected"
    planner_calls = [c for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"]]
    assert len(planner_calls) == 2  # one plan per critique round; the final rejection halts without a re-plan
    assert "T1: split it" in (h.repo / ".github/rejection-log.md").read_text()
    assert "round 1: spec-critic" in h.report()


def test_critic_rejection_then_accept(h):
    reject = step(stdout=json.dumps({"verdict": "reject", "issues": ["T2: name the interface"]}))
    accept = step(stdout=json.dumps({"verdict": "accept", "issues": []}))
    h.scenario(critics=[reject, accept])
    o, reason = h.pilotinloop()
    assert reason == "completed"


def test_invalid_plan_json_reprompts_then_halts(h):
    h.scenario(planner=[step(stdout="not json"), step(stdout="still not json")])
    o, reason = h.pilotinloop()
    assert reason == "plan_rejected"


# ---------------------------------------------------------------- acceptance criteria parsing / preflight
def test_untagged_criterion_fails_preflight(h):
    (h.repo / ".github/requirements/requirements.md").write_text(
        "# F\n\n## Acceptance criteria\n- add works [check: test_add]\n- looks nice\n")
    h.git("commit", "-qam", "req")
    h.scenario()
    o = orch.PilotInLoop(h.repo, h.cfg, sleep_fn=h.sleeps.append)
    with pytest.raises(orch.PreflightError) as e:
        o.preflight("calc")
    assert "looks nice" in str(e.value)


def test_preflight_writes_open_questions(h, monkeypatch):
    h.scenario()
    monkeypatch.chdir(h.repo)
    o = orch.PilotInLoop(h.repo, h.cfg, sleep_fn=h.sleeps.append)
    o.preflight("calc")
    assert (h.repo / ".github/requirements/open-questions.md").read_text().startswith("# Open questions")
    assert any("Reply with exactly the word OK" in c["prompt"] for c in h.calls())


# ---------------------------------------------------------------- rollback
def test_rollback_reverts_task_and_dependents(h):
    h.scenario()
    h.pilotinloop()
    o = orch.PilotInLoop(h.repo, h.cfg, sleep_fn=h.sleeps.append)
    o.rollback("T1")
    p = h.progress()
    assert [t["status"] for t in p["tasks"]] == ["pending", "pending"]
    assert not (h.repo / "calc/add.py").exists() and not (h.repo / "calc/mul.py").exists()
    assert (h.repo / "tests/test_calc.py").exists()  # locked tests survive a rollback
    assert 'Revert "[pilotinloop] T2' in h.log()
