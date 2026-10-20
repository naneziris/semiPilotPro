import json
import shutil
from pathlib import Path

import pytest

from semipilot import orchestrator as orch
from conftest import task_of, ADD_BAD, ADD_OK, MUL_OK, PLAN, QUESTIONS, SPEC, TEST_FILE_GOOD, TEST_FILE_MUL, step, write


# ---------------------------------------------------------------- happy path
def test_happy_path_two_tasks(h):
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    p = h.progress()
    assert [t["status"] for t in p["tasks"]] == ["done", "done"]
    assert [t["attempts"] for t in p["tasks"]] == [1, 1]
    log = h.log()
    assert "feat(calc): add function (T1)" in log and "feat(calc): mul function (T2)" in log
    assert "test(calc): acceptance tests (locked)" in log and "chore(calc): run state (completed)" in log
    assert "semipilot" not in log.lower()  # no bot marker anywhere in history
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "feat/calc"
    assert h.git("status", "--porcelain").strip() == ""  # state committed, logs ignored
    # plan.json lives outside the repo during the run and is copied into the feature folder at the end
    assert (h.state / "repo" / p["run_id"] / "plan.json").exists()
    assert (h.feat / "plan.json").exists()
    rep = h.report()
    assert "Stop reason: **completed**" in rep and "T2" in rep and "PR description draft" in rep
    plan_md = (h.feat / "implementation-plan.md").read_text()
    assert "### T1 — add function" in plan_md and "Knowledge Updates Required" in plan_md
    assert "semipilot-scribe" not in rep  # no knowledge layer → no scribe step
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
    assert "feat/calc" not in h.git("branch")  # no branch created yet
    # human answers inline and commits, then the run proceeds and the planner sees the answers
    (h.feat / "open-questions.md").write_text(QUESTIONS.replace("- Answer:", "- Answer: ints only"))
    h.git("add", "-A")
    h.git("commit", "-qm", "answers")
    o, reason = h.run()
    assert reason == "completed"
    plan_prompt = next(c["prompt"] for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"])
    assert "open-questions.md" in plan_prompt
    assert sum(1 for c in h.calls() if "questions-only mode" in task_of(c["prompt"])) == 1  # not asked twice


def test_uncommitted_answers_are_committed_for_you(h):
    h.scenario(questions=[step(stdout=QUESTIONS)])
    with pytest.raises(orch.NeedsAnswers):
        h.run()
    (h.feat / "open-questions.md").write_text(QUESTIONS.replace("- Answer:", "- Answer: ints only"))
    o, reason = h.run()  # no git add/commit by the human
    assert reason == "completed"
    assert "docs(calc): spec and answers" in h.log()


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
    assert not any("questions-only mode" in task_of(c["prompt"]) for c in h.calls())


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
    assert reason == "completed_with_blocked"  # not "completed": tasks are left blocked


def test_error_signature_ignores_line_numbers_and_paths():
    a = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/x/calc/add.py:12: AssertionError"
    b = "FAILED tests/test_calc.py::test_add - assert 1 == 5\n/tmp/y/calc/add.py:37: AssertionError"
    c = "FAILED tests/test_calc.py::test_mul - assert 1 == 6"
    assert orch.error_signature(a) == orch.error_signature(b)
    assert orch.error_signature(a) != orch.error_signature(c)


# ---------------------------------------------------------------- infra failures
def test_502_never_marks_task_blocked(h):
    h.scenario(implementer_t1=[step(exit=1, stderr=h.err["transient"]),
                               step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.run()
    assert reason == "completed"
    t1 = h.task("T1")
    assert t1["status"] == "done" and t1["attempts"] == 1
    assert h.progress()["infra"]["transient_failures"] == 1
    assert "Transient agent failures: 1" in h.report()
    assert f"Harness: {h.harness}" in h.report()


def test_breaker_leaves_task_pending_and_resume_finishes(h):
    h.cfg["infra"].update({"max_outage_seconds": 0.03, "backoff_start_seconds": 0.02, "backoff_cap_seconds": 0.02})
    h.scenario(implementer_t1=[step(exit=1, stderr=h.err["outage"])] * 5 + [
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.run()
    assert reason == "agent_unavailable"
    assert h.task("T1")["status"] == "pending" and h.task("T2")["status"] == "pending"
    assert h.git("status", "--porcelain").strip() == ""
    h.cfg["infra"].update({"max_outage_seconds": 5400})
    o, reason = h.resume()
    assert reason == "completed"
    assert [t["status"] for t in h.progress()["tasks"]] == ["done", "done"]


def test_401_halts_immediately_with_auth_failure(h):
    h.scenario(implementer_t1=[step(exit=1, stderr=h.err["fatal"])])
    o, reason = h.run()
    assert reason == "auth_failure" and h.task("T1")["status"] == "pending" and h.sleeps == []


def test_quota_exhaustion_halts_without_backoff(h):
    h.scenario(implementer_t1=[step(exit=1, stderr=h.err["quota"])])
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
    assert not h.calls()  # no agent call before the cheap checks pass


def test_missing_spec_points_to_the_skills(h):
    (h.feat / "requirements.md").unlink()
    h.git("commit", "-qam", "rm")
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "/semipilot-refine" in str(e.value) and "/semipilot-spec-critic" in str(e.value)


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
    assert 'Revert "feat(calc): mul function (T2)' in h.log()


# ---------------------------------------------------------------- knowledge layer integration
KB_PY = Path(__file__).resolve().parents[1] / "skills" / "semipilot-knowledge" / "scripts" / "kb.py"
CARD = """---
id: app.{slug}
owns: [{tag}]
code:
  - {code}
---
{body}
"""


def install_kl(h, healthy=True, tags="calc, math"):
    """A real (tiny) knowledge layer: vocabulary, two cards, scripts/kb/kb.py."""
    (h.repo / "docs/cards").mkdir(parents=True)
    (h.repo / "docs/cards/_vocabulary.md").write_text("# Vocabulary\n\n- `calc` — arithmetic\n- `math` — maths helpers\n")
    (h.repo / "calc").mkdir()
    (h.repo / "calc/README.md").write_text("calc package\n")
    (h.repo / "NOTES.md").write_text("notes\n")
    (h.repo / "docs/cards/calc.md").write_text(CARD.format(slug="calc", tag="calc", code="calc/", body="Arithmetic helpers." if healthy else ""))
    (h.repo / "docs/cards/math.md").write_text(CARD.format(slug="math", tag="math", code="NOTES.md", body="Maths notes."))
    (h.repo / "scripts/kb").mkdir(parents=True)
    shutil.copy(KB_PY, h.repo / "scripts/kb/kb.py")
    (h.feat / "requirements.md").write_text((h.feat / "requirements.md").read_text() + f"\n## Knowledge References\n- Tags: {tags}\n")
    h.git("add", "-A")
    h.git("commit", "-qm", "kl")


def test_knowledge_layer_is_validated_and_resolved_for_every_agent(h):
    install_kl(h)
    h.scenario(planner=[step(stdout=json.dumps({**PLAN, "knowledge_updates": ["docs/cards/calc.md: add mul to public_contracts"]}))])
    o, reason = h.run()
    assert reason == "completed"
    assert o.kl and o.tags() == ["calc", "math"]
    assert "scripts/kb/kb.py validate" in o.kb_validate_cmd
    for c in h.calls():
        if "Reply with exactly" in c["prompt"]:
            continue
        # the orchestrator resolved the tags itself; the agent gets the reading list, not a command to run
        assert "## Read these cards (L1)" in c["prompt"] and "docs/cards/calc.md" in c["prompt"], c["prompt"][:300]
        assert "kb.py resolve" not in c["prompt"]
    assert "add mul to public_contracts" in (h.feat / "implementation-plan.md").read_text()
    assert "semipilot-scribe" in h.report()


def test_unknown_tag_fails_preflight_before_any_agent_call(h):
    install_kl(h, tags="calc, nosuchtag")
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "unknown tag" in str(e.value) and "Knowledge References" in str(e.value)
    assert not h.calls()


def test_unhealthy_knowledge_layer_blocks_preflight(h):
    install_kl(h, healthy=False)
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "knowledge layer unhealthy" in str(e.value) and "prose body is empty" in str(e.value)
    assert not h.calls()


def test_knowledge_layer_can_be_switched_off(h):
    install_kl(h, healthy=False)
    h.cfg["knowledge_layer"]["mode"] = "off"
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_legacy_node_knowledge_layer_still_works(h):
    """Repositories set up before v0.2 have the Node scripts; they keep working until `semipilot kb init --force`."""
    (h.repo / "docs/cards").mkdir(parents=True)
    (h.repo / "docs/cards/_vocabulary.md").write_text("- `calc`\n")
    (h.repo / "scripts/kb").mkdir(parents=True)
    (h.repo / "scripts/kb/kb-validate.mjs").write_text("process.exit(0)")
    (h.repo / "scripts/kb/kb-resolve.mjs").write_text("console.log('## Read these cards (L1)\\ndocs/cards/calc.md')")
    (h.feat / "requirements.md").write_text((h.feat / "requirements.md").read_text() + "\n## Knowledge References\n- Tags: calc\n")
    h.git("add", "-A")
    h.git("commit", "-qm", "kl")
    h.scenario()
    o, reason = h.run()
    assert reason == "completed" and o.kb_validate_cmd.startswith("node ")
    impl = [c["prompt"] for c in h.calls() if "Implement **only task" in c["prompt"]]
    assert impl and all("docs/cards/calc.md" in p for p in impl)


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


# ------------------------------------------------------------------ project in a subfolder of the repo
def test_project_in_subfolder_of_monorepo(h_sub):
    h = h_sub
    assert h.repo != h.git_root
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    assert [t["status"] for t in h.progress()["tasks"]] == ["done", "done"]
    assert o.git.prefix == "apps/api/"
    log = h.log()
    assert "feat(calc): add function (T1)" in log and "test(calc): acceptance tests (locked)" in log
    assert h.git("status", "--porcelain").strip() == ""
    # everything landed under the project, nothing at the git root
    assert (h.repo / "calc" / "add.py").exists() and not (h.git_root / "calc").exists()
    assert (h.feat / "plan.json").exists()
    # the sibling app is untouched
    assert (h.git_root / "apps" / "web" / "index.js").read_text() == "// sibling app\n"
    # git paths are project-relative in the state (used for locked-test checks and rollbacks)
    assert h.task("T1")["diff"]["files"] >= 1
    assert all(not f.startswith("apps/") for f in o.git.changed_files("HEAD~1") + [t for t in o.git.status_paths()])


def test_subfolder_rollback_restores_project_relative_paths(h_sub):
    """A locked-test violation is reverted via `git cat-file`/`checkout` with the project prefix."""
    h = h_sub
    h.scenario(implementer_t1=[
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK), write("tests/test_calc.py", "# tampered\n")]),
        step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)]),
    ])
    o, reason = h.run()
    assert reason == "completed"
    assert (h.repo / "tests" / "test_calc.py").read_text() == TEST_FILE_GOOD
    assert h.task("T1")["attempts"] == 2


def test_subfolder_dirty_sibling_blocks_the_run(h_sub):
    """The clean-tree check is repo-wide on purpose: rollbacks use `git reset --hard`, which cannot be scoped."""
    h = h_sub
    (h.git_root / "apps" / "web" / "index.js").write_text("// edited, uncommitted\n")
    h.scenario()
    with pytest.raises(orch.PreflightError, match="dirty"):
        h.run()


# ------------------------------------------------------------------ the run branches off the branch you are on
def test_run_says_which_branch_it_starts_from(h):
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    log = (h.feat / "implementation-progress.json").read_text()
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip() == o.progress.branch
    assert h.git("merge-base", "main", o.progress.branch).strip() == h.git("rev-parse", "main").strip()


def test_run_refuses_to_start_from_another_semipilot_branch_unless_stack(h):
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    first = o.progress.branch
    # second feature, standing on the first feature's branch
    feat2 = h.repo / ".semipilot" / "features" / "calc2"
    feat2.mkdir()
    (feat2 / "requirements.md").write_text(SPEC.replace("feature: calc", "feature: calc2").replace("Requirement: calc", "Requirement: calc2"))
    h.git("add", "-A"); h.git("commit", "-q", "-m", "spec calc2")
    o2 = orch.Loop(h.repo, h.cfg, "calc2", sleep_fn=h.sleeps.append)
    with pytest.raises(orch.PreflightError, match="branch of an earlier semipilot run"):
        h._in_repo(lambda: o2.run(preflight_only=True))
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip() == first  # nothing happened
    # explicitly allowed: the preflight passes and the branch would be made from the first feature's branch
    o3 = orch.Loop(h.repo, h.cfg, "calc2", sleep_fn=h.sleeps.append)
    assert h._in_repo(lambda: o3.run(preflight_only=True, stack=True)) == "preflight_ok"


def test_branch_name_follows_config_and_spec_type(h):
    o = h.loop()
    assert o.branch_name() == "feat/calc"
    (h.feat / "requirements.md").write_text(SPEC.replace("status: approved", "status: approved\ntype: fix"))
    assert o.branch_name() == "fix/calc"
    cfg = json.loads(json.dumps(h.cfg))
    cfg["git"]["branch"] = "feature/{feature}-{date}"
    o2 = h.loop(cfg)
    assert o2.branch_name().startswith("feature/calc-20")
    legacy = json.loads(json.dumps(h.cfg)); del legacy["git"]["branch"]; legacy["git"]["branch_prefix"] = "sp/"
    assert h.loop(legacy).branch_name().startswith("sp/calc-20")


def test_commit_messages_follow_config_and_spec_type(h):
    o = h.loop()
    assert o.commit_message("Add function (T1)") == "feat(calc): add function (T1)"
    assert o.commit_message("acceptance tests", kind="test") == "test(calc): acceptance tests"
    (h.feat / "requirements.md").write_text(SPEC.replace("status: approved", "status: approved\ntype: fix"))
    assert o.commit_message("handle zero (T1)") == "fix(calc): handle zero (T1)"
    legacy = json.loads(json.dumps(h.cfg)); del legacy["git"]["commit"]; legacy["git"]["commit_prefix"] = "[bot]"
    assert h.loop(legacy).commit_message("Add function (T1)") == "[bot] add function (T1)"



# ---------------------------------------------------------------- harness-neutral loop (v0.2)
def test_role_definitions_are_inlined_not_loaded_as_agents(h):
    h.scenario()
    h.run()
    calls = h.calls()
    planner = [c for c in calls if "questions-only mode" in task_of(c["prompt"]) or "Output **only** a JSON object matching" in c["prompt"]]
    assert planner and all("PilotInLoop planner" in c["prompt"] and "\n# Your task\n" in c["prompt"] for c in planner)
    critics = [c for c in calls if "You are the spec-critic" in c["prompt"] or "You are the plan-critic" in c["prompt"]]
    assert any("PilotInLoop spec critic" in c["prompt"] for c in critics)
    assert any("PilotInLoop plan critic" in c["prompt"] for c in critics)
    for c in calls:
        assert "--agent" not in c["argv"]
        assert c["dialect"] == h.harness


def test_read_only_roles_never_get_write_tools(h):
    h.scenario()
    h.run()
    write = "--allow-tool=write" if h.harness == "copilot" else "Edit"
    for c in h.calls():
        t = task_of(c["prompt"])
        reading = "questions-only mode" in t or "Output **only** a JSON object" in t or "You are the spec-critic" in t or "You are the plan-critic" in t
        if reading:
            assert write not in c["argv"], t[:80]
        elif "Implement **only task" in t:
            assert write in c["argv"]


def test_claude_prompts_go_through_stdin_and_cost_is_reported(h):
    h.scenario()
    h.run()
    if h.harness == "claude":
        assert all(c["stdin"] for c in h.calls())
        assert all("--no-session-persistence" in c["argv"] for c in h.calls())
        assert h.progress()["budget"]["cost_usd"] > 0
        assert "Cost reported by the harness" in h.report()
    else:
        assert "Cost reported by the harness" not in h.report()


def test_agent_switching_branches_halts_the_run(h):
    h.scenario(implementer_t1=[step(actions=[{"git": ["checkout", "-q", "-b", "sneaky"]}])])
    o, reason = h.run()
    assert reason == "guardrail_violation"
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "feat/calc"
    assert "switched the branch to sneaky" in h.report()


def test_role_override_from_project_folder(h):
    roles = h.repo / ".semipilot" / "roles"
    roles.mkdir(parents=True)
    (roles / "plan-critic.md").write_text("HOUSE RULES PLAN CRITIC. Instructions: {instructions}\n")
    h.git("add", "-A")
    h.git("commit", "-qm", "role override")
    h.scenario()
    h.run()
    crit = [c["prompt"] for c in h.calls() if "You are the plan-critic" in c["prompt"]]
    assert crit and all(p.startswith("HOUSE RULES PLAN CRITIC") for p in crit)


# ---------------------------------------------------------------- review fixes (0.2.0)
def test_frontmatter_comments_do_not_break_approval_or_branch(h):
    (h.feat / "requirements.md").write_text(SPEC.replace("status: approved", "type: fix   # conventional type\nstatus: approved   # set by the spec critic"))
    h.git("commit", "-qam", "commented frontmatter")
    h.scenario()
    o, reason = h.run()
    assert reason == "completed" and h.progress()["branch"] == "fix/calc"


def test_blocked_planner_halts_with_the_question(h):
    h.scenario(planner=[step(stdout="I read everything.\nBLOCKED: should totals include tax?")])
    o, reason = h.run()
    assert reason == "blocked" and "should totals include tax?" in h.report()
    assert sum(1 for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"]) == 1  # not re-asked


def test_blocked_implementer_blocks_the_task_with_its_question(h):
    h.scenario(implementer_t1=[step(stdout="BLOCKED: which rounding mode?", actions=[write("calc/add.py", ADD_BAD)])])
    o, reason = h.run()
    t1 = h.task("T1")
    assert t1["status"] == "blocked" and t1["blocked_reason"] == "BLOCKED: which rounding mode?" and t1["attempts"] == 1
    assert not (h.repo / "calc/add.py").exists() and reason == "completed_with_blocked"


def test_a_failing_pre_commit_hook_does_not_crash_the_loop(h):
    hooks = h.git_root / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n")
    (hooks / "pre-commit").chmod(0o755)
    h.scenario()
    o, reason = h.run()
    assert reason == "completed"
    o.rollback("T2")  # reverts commit through the hook too
    assert h.task("T2")["status"] == "pending"


def test_transient_error_after_a_branch_switch_never_resets_the_other_branch(h):
    h.scenario(implementer_t1=[step(exit=1, stderr=h.err["transient"], actions=[{"git": ["checkout", "-q", "main"]}])])
    o, reason = h.run()
    assert reason == "guardrail_violation"
    assert h.git("rev-parse", "main").strip() == h.progress()["base_commit"]  # main was not reset to the run's commits
    assert h.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "feat/calc"


@pytest.mark.parametrize("line,ok", [("- Tags: calc;touch${IFS}pwned", False), ("- **Tags:** calc, math", True)])
def test_knowledge_tags_are_validated_before_reaching_a_shell(h, line, ok):
    install_kl(h)
    text = (h.feat / "requirements.md").read_text().replace("- Tags: calc, math", line)
    (h.feat / "requirements.md").write_text(text)
    h.git("commit", "-qam", "tags")
    h.scenario()
    if ok:
        o, reason = h.run()
        assert reason == "completed" and o.tags() == ["calc", "math"]
    else:
        with pytest.raises(orch.PreflightError) as e:
            h.run()
        assert "invalid knowledge tag" in str(e.value) and not (h.repo / "pwned").exists()


def test_claude_turn_cap_is_a_task_failure_not_an_outage(h):
    if h.harness != "claude":
        pytest.skip("structured result subtypes are Claude Code's")
    capped = step(exit=1, stdout="", claude_json={"subtype": "error_max_turns", "result": ""})
    h.scenario(implementer_t1=[capped, capped, capped])
    o, reason = h.run()
    assert h.progress()["infra"]["transient_failures"] == 0 and h.sleeps == []
    assert h.task("T1")["status"] == "blocked"


def test_claude_api_status_drives_classification(h):
    if h.harness != "claude":
        pytest.skip("api_error_status is Claude Code's")
    h.scenario(implementer_t1=[step(exit=1, stdout="boom", claude_json={"api_error_status": 529}),
                               step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    o, reason = h.run()
    assert reason == "completed" and h.progress()["infra"]["transient_failures"] == 1


def test_cost_includes_the_preflight_calls(h):
    if h.harness != "claude":
        pytest.skip("cost is reported by Claude Code")
    h.scenario()
    h.run()
    assert round(h.progress()["budget"]["cost_usd"], 2) == round(0.01 * len(h.calls()), 2)


def test_resume_after_a_blocked_planner_plans_writes_tests_and_builds(h):
    h.scenario(planner=[step(stdout="BLOCKED: ints or floats?"), step(stdout=json.dumps(PLAN))])
    o, reason = h.run()
    assert reason == "blocked"
    o, reason = h.resume()  # the human answered in the requirements; the loop picks up at planning
    assert reason == "completed" and [t["status"] for t in h.progress()["tasks"]] == ["done", "done"]
    assert "test(calc): acceptance tests (locked)" in h.log()


def test_resume_gives_a_blocked_task_fresh_attempts(h):
    bad = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_BAD)])
    good = step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])
    h.scenario(implementer_t1=[bad, bad, good])
    o, reason = h.run()
    assert reason == "completed_with_blocked" and h.task("T1")["status"] == "blocked"
    o, reason = h.resume()
    assert reason == "completed" and h.task("T1")["status"] == "done"


# ---------------------------------------------------------------- cost (0.2.0)
def test_preflight_makes_no_model_call_of_its_own(h):
    h.scenario()
    h.run()
    assert not any("Reply with exactly" in c["prompt"] for c in h.calls())
    assert len(h.calls()) == 1 + 1 + 2 + 1 + 2  # questions, plan, 2 critics, test-writer, 2 tasks


def test_missing_agent_cli_fails_preflight_for_free(h):
    h.cfg["runner"]["command"] = "definitely-not-installed-agent-xyz"
    h.scenario()
    with pytest.raises(orch.PreflightError) as e:
        h.run()
    assert "not found" in str(e.value)


def test_models_per_role_and_cost_by_role(h):
    h.cfg["models"]["implementer"] = "cheap-model"
    h.cfg["runner"]["model"] = "strong-model"
    h.scenario()
    h.run()
    for c in h.calls():
        model = c["argv"][c["argv"].index("--model") + 1]
        assert model == ("cheap-model" if "Implement **only task" in c["prompt"] else "strong-model")
    if h.harness == "claude":
        by_role = h.progress()["budget"]["cost_by_role"]
        assert round(by_role["implementer"], 2) == 0.02 and "by role:" in h.report()
