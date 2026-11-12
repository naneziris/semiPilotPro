"""Risk tiers: how much of a run a feature may do without a human (risk.py and the loop's two gates)."""
import json

import pytest

from semipilot import cli, orchestrator as orch, risk



# ---------------------------------------------------------------- the rules, without a loop
def test_path_matches_globs_and_top_level_folders():
    assert risk.path_matches("src/auth/login.py", "**/auth/**")
    assert risk.path_matches("auth/login.py", "**/auth/**")          # `**/x/**` also means a top-level x/
    assert risk.path_matches("db/migrations/001.sql", "**/*.sql")
    assert risk.path_matches("schema.sql", "**/*.sql")
    assert risk.path_matches("billing/invoice.py", "billing/")       # a folder pattern covers everything under it
    assert not risk.path_matches("src/author/x.py", "**/auth/**")
    assert not risk.path_matches("src/calc/add.py", "**/auth/**")


def test_assess_declared_default_and_escalation(hc):
    cfg = hc.cfg
    assert risk.assess({}, cfg)["effective"] == "low" and risk.assess({}, cfg)["declared"] is None
    r = risk.assess({"risk": "High"}, cfg)
    assert r["effective"] == "high" and r["gates"] == {"plan_approval": True, "task_review": True}
    # the plan's paths can raise the tier, never lower it
    r = risk.assess({"risk": "low"}, cfg, ["src/auth/session.py", "src/ui/button.py"])
    assert r["effective"] == "medium" and r["escalated_by"] == ["src/auth/session.py"]
    r = risk.assess({"risk": "high"}, cfg, ["src/auth/session.py"])
    assert r["effective"] == "high" and r["escalated_by"] == []
    cfg["autonomy"]["escalate"]["high"] = ["**/payments/**"]
    assert risk.assess({"risk": "medium"}, cfg, ["payments/charge.py"])["effective"] == "high"


def test_tier_gates_are_configuration(hc):
    hc.cfg["autonomy"]["tiers"]["medium"] = {"task_review": True}
    assert risk.gates(hc.cfg, "medium") == {"plan_approval": True, "task_review": True}
    assert risk.gates(hc.cfg, "low") == {"plan_approval": False, "task_review": False}


def test_invalid_risk_is_refused_before_anything_is_spent(hc):
    hc.set_spec(risk="extreme")
    hc.scenario()
    with pytest.raises(orch.PreflightError) as e:
        hc.run()
    assert "extreme" in str(e.value) and "low, medium, high" in str(e.value)
    assert hc.calls() == []


def test_require_risk_refuses_requirements_without_a_tier(hc):
    hc.cfg["autonomy"]["require_risk"] = True
    hc.scenario()
    with pytest.raises(orch.PreflightError) as e:
        hc.run()
    assert "names no risk tier" in str(e.value)
    hc.set_spec(risk="low")
    _, reason = hc.run()
    assert reason == "completed"


# ---------------------------------------------------------------- low: nothing stops the run
def test_low_risk_runs_straight_through(h):
    h.set_spec(risk="low")
    h.scenario()
    _, reason = h.run()
    assert reason == "completed"
    p = h.progress()
    assert p["risk"]["effective"] == "low" and p["risk"]["declared"] == "low"
    assert "Risk tier: **low**" in h.report()


# ---------------------------------------------------------------- medium: one stop to approve the plan
def test_medium_risk_stops_for_plan_approval_then_continues(h):
    h.set_spec(risk="medium")
    h.scenario()
    o, reason = h.run()
    assert reason == "plan_approval"
    p = h.progress()
    assert p["tests_commit"] is None and [t["status"] for t in p["tasks"]] == ["pending", "pending"]
    assert "semipilot approve calc" in p["stop_detail"]
    assert (h.feat / "implementation-plan.md").exists()          # the thing the human reads
    assert not any("You are the test-writer" in c["prompt"] for c in h.calls())  # no code, no tests yet
    # resuming without approving stops at the same place, at no cost
    n = len(h.calls())
    _, reason = h.resume()
    assert reason == "plan_approval" and len(h.calls()) == n
    # approve, resume: the run finishes and remembers who let it through
    h.do(lambda: h.loop().approve_plan())
    _, reason = h.resume()
    assert reason == "completed"
    p = h.progress()
    assert p["plan_approval"]["plan_sha"] and [t["status"] for t in p["tasks"]] == ["done", "done"]
    assert "Plan approved by a human" in h.report()
    assert sum(1 for c in h.calls() if "Output **only** a JSON object matching" in c["prompt"]) == 1  # planned once


def test_replan_hands_the_humans_words_to_the_planner(hc):
    hc.set_spec(risk="medium")
    hc.scenario()
    _, reason = hc.run()
    assert reason == "plan_approval"
    hc.do(lambda: hc.loop().request_replan("put mul in the same module as add"))
    p = hc.progress()
    assert p["stop_reason"] == "replan_requested" and p["tasks"] == [] and not (hc.feat / "plan.json").exists()
    assert "human review of the plan" in (hc.feat / "rejection-log.md").read_text()
    _, reason = hc.resume()
    assert reason == "plan_approval"                           # a new plan is a new thing to approve
    plans = [c["prompt"] for c in hc.calls() if "Output **only** a JSON object matching" in c["prompt"]]
    assert len(plans) == 2 and "put mul in the same module as add" in plans[1]
    assert "outranks the critics" in plans[1]
    assert hc.progress()["plan_feedback"] == ""                # consumed
    hc.do(lambda: hc.loop().approve_plan())
    _, reason = hc.resume()
    assert reason == "completed"


def test_replan_needs_words_and_a_waiting_plan(hc):
    hc.scenario()
    hc.run()                                                    # low risk: completed, nothing waits
    with pytest.raises(orch.PreflightError) as e:
        hc.do(lambda: hc.loop().request_replan("x"))
    assert "not ready for that" in str(e.value)
    with pytest.raises(orch.PreflightError):
        hc.do(lambda: hc.loop().approve_plan())


def test_plan_touching_a_sensitive_path_raises_the_tier(hc):
    hc.cfg["autonomy"]["escalate"]["medium"] = ["calc/**"]      # the plan's files are calc/add.py, calc/mul.py
    hc.scenario()                                               # the spec names no risk: default low
    _, reason = hc.run()
    assert reason == "plan_approval"
    r = hc.progress()["risk"]
    assert r["declared"] is None and r["effective"] == "medium" and "calc/add.py" in r["escalated_by"]
    assert "raised from the default" in hc.report()


def test_an_approved_plan_that_changes_needs_approval_again(hc):
    hc.set_spec(risk="medium")
    hc.scenario()
    hc.run()
    hc.do(lambda: hc.loop().approve_plan())
    # somebody edits the plan after the approval: the approval no longer covers it
    plan_file = hc.state / "repo" / hc.progress()["run_id"] / "plan.json"
    changed = json.loads(plan_file.read_text())
    changed["tasks"][0]["description"] += " And also email the result to everyone."
    plan_file.write_text(json.dumps(changed))
    _, reason = hc.resume()
    assert reason == "plan_approval"


# ---------------------------------------------------------------- high: one stop after every task
def test_high_risk_stops_after_each_task_until_the_last(h):
    h.set_spec(risk="high")
    h.scenario()
    _, reason = h.run()
    assert reason == "plan_approval"
    h.do(lambda: h.loop().approve_plan())
    _, reason = h.resume()
    assert reason == "task_review"
    p = h.progress()
    assert h.task("T1")["status"] == "done" and h.task("T1")["review"] == "pending"
    assert h.task("T2")["status"] == "pending"
    assert "git show" in p["stop_detail"] and "semipilot rollback calc T1" in p["stop_detail"]
    assert p["review"] == {}                                    # the reviewer agent waits for the end of the run
    # resume = "I read T1, go on". T2 is the last task: the end of the run is its review.
    _, reason = h.resume()
    assert reason == "completed"
    assert h.task("T1")["review"] == "accepted" and "review" not in h.task("T2")
    assert h.progress()["review"]["verdict"] == "ship"


def test_rejecting_a_task_at_its_review_redoes_it(hc):
    hc.set_spec(risk="high")
    hc.scenario()
    hc.run()
    hc.do(lambda: hc.loop().approve_plan())
    hc.resume()
    hc.do(lambda: hc.loop().rollback("T1"))
    assert hc.task("T1")["status"] == "pending" and "review" not in hc.task("T1")
    _, reason = hc.resume()
    assert reason == "task_review" and hc.task("T1")["review"] == "pending"   # built again, waits again
    assert hc.task("T1")["attempts"] == 1


# ---------------------------------------------------------------- the command line
def run_cli(h, *args):
    return h.do(lambda: cli.main(["--repo", str(h.repo), *args]))


def test_cli_gates_exit_3_and_say_whose_turn_it_is(hc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda repo, path=None: hc.cfg)
    hc.set_spec(risk="medium")
    hc.scenario()
    assert run_cli(hc, "run", "calc") == 3
    out = capsys.readouterr().out
    assert "Your turn:" in out and "[plan_approval]" in out and "semipilot approve calc" in out
    assert run_cli(hc, "status") == 0
    assert "waiting for you: approve the plan (medium risk)" in capsys.readouterr().out
    assert run_cli(hc, "approve", "calc") == 0                 # records the approval and continues to the end
    assert hc.progress()["stop_reason"] == "completed"


def test_cli_replan_and_approve_without_running(hc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda repo, path=None: hc.cfg)
    hc.set_spec(risk="medium")
    hc.scenario()
    run_cli(hc, "run", "calc")
    assert run_cli(hc, "replan", "calc", "-m", "one task only", "--no-run") == 0
    assert hc.progress()["stop_reason"] == "replan_requested"
    assert run_cli(hc, "resume", "calc") == 3
    assert run_cli(hc, "approve", "calc", "--no-run") == 0
    assert hc.progress()["stop_reason"] == "plan_approval" and hc.progress()["plan_approval"]["at"]
    assert run_cli(hc, "resume", "calc") == 0
