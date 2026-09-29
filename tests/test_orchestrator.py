import json

import pytest

from semipilot import orchestrator as orch
from conftest import ADD_BAD, ADD_OK, MUL_OK, PLAN, QUESTIONS, TEST_FILE_GOOD, TEST_FILE_MUL, step, write


# ---------------------------------------------------------------- happy path
def test_happy_path_two_tasks(h):
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    p = h.progress()
    assert [t["status"] for t in p["tasks"]] == ["done", "done"]
    assert [t["attempts"] for t in p["tasks"]] == [1, 1]
    log = h.log()
    assert "[semipilot] T1: add function" in log and "[semipilot] T2: mul function" in log
    assert "[semipilot] tests: locked acceptance tests" in log
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip().startswith("semipilot/calc-")
    assert h.git("status", "--porcelain").strip() == ""  # state committed, logs ignored
    # plan.json lives outside the repo during the run and is copied into the feature folder at the end
    assert (h.state / "repo" / p["run_id"] / "plan.json").exists()
    assert (h.feat / "plan.json").exists()
    rep = h.report()
    assert "Stop reason: **completed**" in rep and "T2" in rep and "PR description draft" in rep
    plan_md = (h.feat / "implementation-plan.md").read_text()
    assert "### T1 — add function" in plan_md and "Knowledge Updates Required" in plan_md
    assert "@scribe" not in rep  # no knowledge layer → no scribe step
    impl_prompts = [c["prompt"] for c in h.calls() if "Implement **only task" in c["prompt"]]
    assert len(impl_prompts) == 2
    assert all("plan.json" not in pr for pr in impl_prompts)
    assert ".semipilot/features/calc/requirements.md" in impl_prompts[0]


def test_every_call_is_a_fresh_process_without_session_flags(h):
    h.scenario()
    h.run()
    for c in h.calls():
        assert not any(a.startswith(("--resume", "--continue", "--session-id")) for a in c["argv"])
        assert "-p" in c["argv"]


# ---------------------------------------------------------------- questions gate
def test_questions_stop_the_run_until_answered(h):
    h.scenario(questions=[step(stdout=QUESTIONS)])
    with pytest.raises(orch.NeedsAnswers) as e:
        h.run()
    assert e.value.count == 1
    assert (h.feat / "open-questions.md").read_text().startswith("# Open questions")
    assert "semipilot/calc-" not in h.git("branch")  # no branch created yet
    # human answers inline and commits, then the run proceeds and the planner sees the answers
    (h.feat / "open-questions.md").write_text(QUESTIONS.replace("- Answer:", "- Answer: ints only"))
    h.git("add", "-A")
    h.git("commit", "-qm", "answers")
    o, reason = h.run()
    assert reason == "completed"
    plan_prompt = next(c["prompt"] for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"])
    assert "open-questions.md" in plan_prompt
    assert sum(1 for c in h.calls() if "questions-only mode" in c["prompt"]) == 1  # not asked twice


def test_uncommitted_answers_are_committed_for_you(h):
    h.scenario(questions=[step(stdout=QUESTIONS)])
    with pytest.raises(orch.NeedsAnswers):
        h.run()
    (h.feat / "open-questions.md").write_text(QUESTIONS.replace("- Answer:", "- Answer: ints only"))
    o, reason = h.run()  # no git add/commit by the human
    assert reason == "completed"
    assert "[semipilot] calc: spec and answers" in h.log()


def test_answered_questions_count():
    n, a = orch.parse_questions(QUESTIONS)
    assert (n, a) == (1, 0)
    n, a = orch.parse_questions(QUESTIONS.replace("- Answer:", "- Answer: yes floats"))
    assert (n, a) == (1, 1)
    multiline = QUESTIONS.replace("- Answer:", "- Answer:\n  ints only, we never need floats")
    assert orch.parse_questions(multiline) == (1, 1)
    assert orch.parse_questions("# Open questions — x\n\nNone.\n") == (0, 0)


def test_no_questions_flag_skips_the_planner_question_pass(h):
    h.scenario(questions=[step(stdout=QUESTIONS)])
    o, reason = h.run(skip_questions=True)
    assert reason == "completed"
    assert not any("questions-only mode" in c["prompt"] for c in h.calls())


# ---------------------------------------------------------------- retry semantics
def test_task_retry_keeps_failed_diff_and_feeds_errors(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)]),
        step(actions=[{"assert_exists": "calc/add.py"}, {"assert_contains": "calc/add.py", "text": "a - b"},
                      write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.run()
    assert reason == "completed"
    assert h.task("T1")["attempts"] == 2
    log2 = next((h.repo / ".semipilot/runs").rglob("T1-attempt2.log")).read_text()
    assert "test_add" in log2 and "still in the working tree" in log2


def test_stuck_detection_blocks_and_resets_tree(h):
    bad = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)])
    h.scenario(implementer_t1=[bad, bad, bad])
    o, reason = h.run()
    t1, t2 = h.task("T1"), h.task("T2")
    assert t1["status"] == "blocked" and t1["attempts"] == 2
    assert t2["status"] == "blocked" and "dependency T1" in t2["blocked_reason"]
    assert not (h.repo / "calc/add.py").exists()
    assert reason == "completed"


def test_error_signature_ignores_line_numbers_and_paths():
    a = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/x/calc/add.py:12: AssertionError"
    b = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/y/calc/add.py:37: AssertionError"
    c = "FAILED tests/test_calc.py::test_mul - assert 1 == 6"
    assert orch.error_signature(a) == orch.error_signature(b)
    assert orch.error_signature(a) != orch.error_signature(c)


# ---------------------------------------------------------------- infra failures
def test_502_never_marks_task_blocked(h):
    h.scenario(implementer_t1=[step(exit=1, stderr="Error: 502 Bad Gateway"),
                               step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.run()
    assert reason == "completed"
    t1 = h.task("T1")
    assert t1["status"] == "done" and t1["attempts"] == 1
    assert h.progress()["infra"]["transient_failures"] == 1
    assert "Transient Copilot failures: 1" in h.report()


def test_breaker_leaves_task_pending_and_resume_finishes(h):
    h.cfg["infra"].update({"max_outage_seconds": 0.03, "backoff_start_seconds": 0.02, "backoff_cap_seconds": 0.02})
    h.scenario(implementer_t1=[step(exit=1, stderr="503 Service Unavailable")] * 5 + [
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.run()
    assert reason == "copilot_unavailable"
    assert h.task("T1")["status"] == "pending" and h.task("T2")["status"] == "pending"
    assert h.git("status", "--porcelain").strip() == ""
    h.cfg["infra"].update({"max_outage_seconds": 5400})
    o, reason = h.resume()
    assert reason == "completed"
    assert [t["status"] for t in h.progress()["tasks"]] == ["done", "done"]


def test_401_halts_immediately_with_auth_failure(h):
    h.scenario(implementer_t1=[step(exit=1, stderr="HTTP 401 Unauthorized: bad credentials")])
    o, reason = h.run()
    assert reason == "auth_failure" and h.task("T1")["status"] == "pending" and h.sleeps == []


def test_quota_exhaustion_halts_without_backoff(h):
    h.scenario(implementer_t1=[step(exit=1, stderr="Copilot premium request quota exceeded for this billing period")])
    o, reason = h.run()
    assert reason == "quota_exhausted" and h.sleeps == [] and h.task("T1")["status"] == "pending"


# ---------------------------------------------------------------- guardrails
def test_test_lock_violation_reverts_tests_and_counts_attempt(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD),
                      write("tests/test_calc.py", "def test_add():\n    assert True\n")]),
        step(actions=[write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.run()
    assert reason == "completed" and h.task("T1")["attempts"] == 2
    assert (h.repo / "tests/test_calc.py").read_text() == TEST_FILE_GOOD
    assert any("modified locked tests" in w for w in h.progress()["warnings"])


def test_implementer_may_add_new_test_files(h):
    h.scenario(implementer_t1=[step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK),
                                             write("tests/test_add_extra.py", "from calc.add import add\ndef test_neg():\n    assert add(-1, 1) == 0\n")])])
    o, reason = h.run()
    assert reason == "completed" and (h.repo / "tests/test_add_extra.py").exists()
    assert any("added new test files" in w for w in h.progress()["warnings"])


def test_scope_violation_touching_other_tasks_files_is_reverted(h):
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK), write("calc/mul.py", MUL_OK)]),
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.run()
    assert reason == "completed" and h.task("T1")["attempts"] == 2
    assert any("scope violation" in w for w in h.progress()["warnings"])


def test_diff_cap_per_task_blocks(h):
    h.cfg["guardrails"]["diff_cap_lines_per_task"] = 3
    h.scenario(implementer_t1=[step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK + "# pad\n" * 10)])])
    h.run()
    assert h.task("T1")["status"] == "blocked" and "cap" in h.task("T1")["blocked_reason"]


def test_iteration_budget_stops_run(h):
    h.cfg["budget"]["max_iterations"] = 1
    h.scenario()
    o, reason = h.run()
    assert reason == "budget_exhausted"
    assert h.task("T1")["status"] == "done" and h.task("T2")["status"] == "pending"


def test_dirty_tree_refused(h):
    (h.repo / "junk.txt").write_text("x")
    h.scenario()
    with pytest.raises(orch.PreflightError):
        h.run()


def test_todo_check_refused(h):
    h.cfg["checks"] = [{"name": "tests", "cmd": "# TODO: your test command"}]
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "TODO" in str(e.value)


# ---------------------------------------------------------------- test contract fix
def test_contract_error_in_locked_tests_gets_one_logged_fix(h):
    wrong_import = TEST_FILE_GOOD.replace("from calc.add import add", "from calc.adder import add")
    h.scenario(test_writer=[step(actions=[write("tests/test_calc.py", wrong_import), write("tests/test_mul.py", TEST_FILE_MUL)])],
               extra={"You are the test-fixer": [step(actions=[write("tests/test_calc.py", TEST_FILE_GOOD)])]})
    o, reason = h.run()
    assert reason == "completed" and h.task("T1")["status"] == "done" and h.task("T1")["contract_fixes"] == 1
    assert "test-fixer edited" in h.report()


def test_contract_fix_is_limited_and_assertion_failures_never_trigger_it(h):
    bad = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)])
    h.scenario(implementer_t1=[bad, bad], extra={"You are the test-fixer": [step(actions=[write("tests/test_calc.py", "def test_add():\n    pass\n")])]})
    h.run()
    assert h.task("T1")["contract_fixes"] == 0
    assert not any("test-fixer" in c["prompt"] for c in h.calls())


# ---------------------------------------------------------------- plan / critique
def test_plan_validation_rules(h):
    crit = [{"ref": "test_add"}, {"ref": "test_mul"}]
    bad = json.loads(json.dumps(PLAN))
    bad["tasks"][0]["expected_files"] = [f"f{i}.py" for i in range(7)]
    bad["tasks"][1]["acceptance_checks"] = ["test_nope"]
    errs = orch.validate_plan(bad, h.cfg, crit)
    assert any("expected_files > max" in e for e in errs)
    assert any("test_mul' is not covered" in e for e in errs)
    assert any("does not match any tagged criterion" in e for e in errs)
    big = json.loads(json.dumps(PLAN))
    big["tasks"][0]["size"] = "L"
    jsonschema = pytest.importorskip("jsonschema")
    if not hasattr(jsonschema, "Draft202012Validator"):
        pytest.skip("schema check needs jsonschema >= 4; the from-source fallback only checks feature/tasks")
    assert any("schema" in e for e in orch.validate_plan(big, h.cfg, crit))
    cyc = json.loads(json.dumps(PLAN))
    cyc["tasks"][0]["depends_on"] = ["T2"]
    assert any("cycle" in e for e in orch.validate_plan(cyc, h.cfg, crit))
    assert orch.validate_plan(PLAN, h.cfg, crit) == []


def test_critic_rejection_replans_then_halts(h):
    reject = step(stdout=json.dumps({"verdict": "reject", "issues": ["T1: split it"]}))
    h.scenario(critics=[reject, reject, reject])
    o, reason = h.run()
    assert reason == "plan_rejected"
    planner_calls = [c for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"]]
    assert len(planner_calls) == 2
    assert "T1: split it" in (h.feat / "rejection-log.md").read_text()
    assert "round 1: spec-critic" in h.report()


def test_critic_rejection_then_accept(h):
    reject = step(stdout=json.dumps({"verdict": "reject", "issues": ["T2: name the interface"]}))
    accept = step(stdout=json.dumps({"verdict": "accept", "issues": []}))
    h.scenario(critics=[reject, accept])
    o, reason = h.run()
    assert reason == "completed"


def test_invalid_plan_json_reprompts_then_halts(h):
    h.scenario(planner=[step(stdout="not json"), step(stdout="still not json")])
    o, reason = h.run()
    assert reason == "plan_rejected"


# ---------------------------------------------------------------- spec gate
def test_untagged_criterion_fails_preflight(h):
    (h.feat / "requirements.md").write_text("---\nstatus: approved\n---\n# F\n\n## Acceptance criteria\n- add works [check: test_add]\n- looks nice\n")
    h.git("commit", "-qam", "spec")
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "looks nice" in str(e.value)


def test_unapproved_spec_refused(h):
    (h.feat / "requirements.md").write_text((h.feat / "requirements.md").read_text().replace("status: approved", "status: draft"))
    h.git("commit", "-qam", "spec")
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "not approved" in str(e.value)
    assert not h.calls()  # no Copilot call before the cheap checks pass


def test_missing_spec_points_to_the_prompts(h):
    (h.feat / "requirements.md").unlink()
    h.git("commit", "-qam", "rm")
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "/refine-requirements" in str(e.value)


# ---------------------------------------------------------------- rollback
def test_rollback_reverts_task_and_dependents(h):
    h.scenario()
    h.run()
    o = h.loop()
    o.rollback("T1")
    p = h.progress()
    assert [t["status"] for t in p["tasks"]] == ["pending", "pending"]
    assert not (h.repo / "calc/add.py").exists() and not (h.repo / "calc/mul.py").exists()
    assert (h.repo / "tests/test_calc.py").exists()
    assert 'Revert "[semipilot] T2' in h.log()


# ---------------------------------------------------------------- knowledge layer integration
def install_fake_kl(h, healthy=True):
    (h.repo / "docs/cards").mkdir(parents=True)
    (h.repo / "docs/cards/_vocabulary.md").write_text("- `calc`\n")
    (h.repo / "scripts/kb").mkdir(parents=True)
    (h.repo / "scripts/kb/kb-validate.mjs").write_text("process.exit(%d)" % (0 if healthy else 1))
    (h.repo / "scripts/kb/kb-resolve.mjs").write_text("console.log('docs/cards/calc.md')")
    (h.feat / "requirements.md").write_text((h.feat / "requirements.md").read_text() + "\n## Knowledge References\n- Tags: calc, math\n")
    h.git("add", "-A")
    h.git("commit", "-qm", "kl")


def test_knowledge_layer_is_validated_and_passed_to_agents(h):
    install_fake_kl(h)
    h.cfg["knowledge_layer"]["validate_cmd"] = "node scripts/kb/kb-validate.mjs"
    h.scenario(planner=[step(stdout=json.dumps({**PLAN, "knowledge_updates": ["docs/cards/calc.md: add mul to public_contracts"]}))])
    o, reason = h.run()
    assert reason == "completed"
    assert o.kl and o.tags() == ["calc", "math"]
    for c in h.calls():
        if "Reply with exactly" in c["prompt"]:
            continue
        assert "kb-resolve.mjs --tags calc,math" in c["prompt"], c["prompt"][:200]
    assert "add mul to public_contracts" in (h.feat / "implementation-plan.md").read_text()
    assert "@scribe" in h.report()


def test_unhealthy_knowledge_layer_blocks_preflight(h):
    install_fake_kl(h, healthy=False)
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "knowledge layer unhealthy" in str(e.value)
    assert not h.calls()


def test_knowledge_layer_can_be_switched_off(h):
    install_fake_kl(h, healthy=False)
    h.cfg["knowledge_layer"]["mode"] = "off"
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"


# ---------------------------------------------------------------- legacy single-feature layout
def test_legacy_github_requirements_layout_is_used_as_is(h):
    import shutil
    legacy = h.repo / ".github/requirements"
    legacy.mkdir(parents=True)
    (legacy / "requirements.md").write_text((h.feat / "requirements.md").read_text())
    shutil.rmtree(h.feat)
    h.git("add", "-A")
    h.git("commit", "-qm", "legacy")
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    assert (legacy / "report.md").exists() and (legacy / "implementation-progress.json").exists()
    assert not h.feat.exists()
