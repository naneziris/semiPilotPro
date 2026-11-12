"""What a run cost: time always, plus what each agent CLI reports (usage.py, the runner's ledger, the report)."""
import json
import os
import time

import pytest

from semipilot import usage
from conftest import NO_QUESTIONS, step, write, ADD_OK

STATS_NEW = """Here is the answer.

Total usage est:        7 Premium requests
API time spent:         2m 59.626s
Total session time:     12m 15.77s
Total code changes:     +206 -77
Breakdown by AI model:
 claude-sonnet-4.5       453.0k in, 13.1k out, 405.7k cached (Est. 7 Premium requests)
 claude-haiku-4.5        1.5k in, 200 out, 0 cached (Est. 0 Premium requests)
"""

STATS_OLD = """Done.

Total usage est:       1 Premium request
Total duration (API):  12.3s
Total duration (wall): 15.1s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    claude-sonnet-4.5    12.3k input, 456 output, 0 cache read, 0 cache write (Est. 1 Premium request)
"""


# ---------------------------------------------------------------- parsing what the CLIs print
def test_copilot_stats_block_current_layout():
    u = usage.parse_copilot_stats(STATS_NEW)
    assert u["premium_requests"] == 7 and u["api_seconds"] == 179.6
    assert u["input_tokens"] == 454500 and u["output_tokens"] == 13300 and u["cached_tokens"] == 405700
    assert u["model"] == "claude-sonnet-4.5, claude-haiku-4.5"


def test_copilot_stats_block_older_layout():
    u = usage.parse_copilot_stats(STATS_OLD)
    assert u == {"premium_requests": 1.0, "api_seconds": 12.3, "input_tokens": 12300, "output_tokens": 456,
                 "cached_tokens": 0, "model": "claude-sonnet-4.5"}


def test_no_stats_block_means_no_usage_and_text_is_untouched():
    assert usage.parse_copilot_stats("just an answer mentioning Premium requests in passing") == {}
    assert usage.strip_copilot_stats("an answer\n") == "an answer\n"
    assert usage.parse_copilot_stats("") == {} and usage.strip_copilot_stats("") == ""


def test_stats_block_is_cut_from_the_answer():
    assert usage.strip_copilot_stats(STATS_NEW) == "Here is the answer.\n"
    assert usage.strip_copilot_stats(STATS_OLD) == "Done.\n"
    with_resume = STATS_NEW + "\nResume this session with copilot --resume=abc-123\n"
    assert usage.strip_copilot_stats(with_resume) == "Here is the answer.\n"
    assert "Premium" not in usage.strip_copilot_stats(STATS_NEW)   # nothing left for the quota patterns to match


def write_session(root, name, events, age=0.0):
    d = root / name
    d.mkdir(parents=True)
    f = d / "events.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    if age:
        old = time.time() - age
        os.utime(f, (old, old))
    return f


SHUTDOWN = {"type": "session.shutdown", "data": {
    "totalPremiumRequests": 3, "totalApiDurationMs": 41500,
    "modelMetrics": {"gpt-5": {"requests": {"count": 4, "cost": 3},
                               "usage": {"inputTokens": 9000, "outputTokens": 700, "cacheReadTokens": 6000}}}}}


def test_copilot_session_shutdown_event(tmp_path):
    root = tmp_path / "session-state"
    write_session(root, "old", [SHUTDOWN], age=3600)                       # an earlier call: too old
    write_session(root, "no-shutdown", [{"type": "session.start", "data": {}}])
    write_session(root, "mine", [{"type": "session.start", "data": {"context": {"cwd": str(tmp_path)}}}, SHUTDOWN])
    u = usage.read_copilot_session(str(root), time.time() - 5, str(tmp_path))
    assert u == {"premium_requests": 3.0, "api_seconds": 41.5, "input_tokens": 9000, "output_tokens": 700,
                 "cached_tokens": 6000, "model": "gpt-5"}


def test_copilot_session_of_another_project_is_not_counted(tmp_path):
    root = tmp_path / "session-state"
    write_session(root, "theirs", [{"type": "session.start", "data": {"context": {"cwd": "/somewhere/else"}}}, SHUTDOWN])
    assert usage.read_copilot_session(str(root), time.time() - 5, str(tmp_path)) == {}
    assert usage.read_copilot_session(str(tmp_path / "missing"), 0, None) == {}
    assert usage.read_copilot_session("", 0, None) == {}


def test_claude_json_usage():
    u = usage.claude_usage({"total_cost_usd": 0.42, "duration_api_ms": 12345, "modelUsage": {"claude-opus-4": {}},
                            "usage": {"input_tokens": 10, "cache_creation_input_tokens": 90,
                                      "cache_read_input_tokens": 1000, "output_tokens": 55}})
    assert u == {"cost_usd": 0.42, "input_tokens": 100, "output_tokens": 55, "cached_tokens": 1000,
                 "api_seconds": 12.3, "model": "claude-opus-4"}
    assert usage.claude_usage({"result": "x"}) == {}


def test_ledger_adds_up_merges_and_prices():
    led = usage.Ledger()
    led.add("planner", 30, {"premium_requests": 1, "input_tokens": 1000, "output_tokens": 100})
    led.add("implementer", 90, {"premium_requests": 2, "input_tokens": 5000, "output_tokens": 900})
    led.add("implementer", 60, None)                                # a call the CLI reported nothing for
    s = led.summary()
    assert s["total"] == {"calls": 3, "seconds": 180.0, "premium_requests": 3, "input_tokens": 6000, "output_tokens": 1000}
    assert s["by_role"]["implementer"]["calls"] == 2
    both = usage.merge(s, s)
    assert both["total"]["calls"] == 6 and both["by_role"]["planner"]["premium_requests"] == 2
    assert usage.merge(None, s) == s and usage.merge({}, {})["total"] == {"calls": 0, "seconds": 0.0}
    assert usage.estimated_cost(s, None) is None                   # requests are not dollars until you say so
    assert usage.estimated_cost(s, 0.04) == 0.12
    assert usage.estimated_cost({"total": {"cost_usd": 1.5, "premium_requests": 10}}, 0.04) == 1.9
    line = usage.describe(s["total"], 0.04)
    assert line == "3 calls, 3.0 min, 3 premium requests, 6.0k in / 1.0k out, $0.12"


# ---------------------------------------------------------------- a whole run
def test_claude_run_reports_tokens_and_cost(tmp_path):
    from conftest import Harness
    h = Harness(tmp_path, harness="claude")
    h.scenario()
    _, reason = h.run()
    assert reason == "completed"
    u = h.progress()["budget"]["usage"]
    assert u["total"]["calls"] == 8 and u["total"]["cost_usd"] == pytest.approx(0.08)
    assert u["total"]["input_tokens"] == 8 * 1200 and u["by_role"]["implementer"]["calls"] == 2
    rep = h.report()
    assert "Agent usage (all loop calls): 8 calls" in rep and "$0.08" in rep
    assert "  - implementer: 2 calls" in rep and "  - reviewer: 1 call," in rep


def test_copilot_run_reads_premium_requests_from_session_files(hc, monkeypatch):
    sessions = hc.git_root.parent / "copilot-sessions"
    monkeypatch.setenv("FAKE_AGENT_SESSION_DIR", str(sessions))
    hc.scenario()
    _, reason = hc.run()
    assert reason == "completed"
    u = hc.progress()["budget"]["usage"]
    assert u["total"]["calls"] == 8 and u["total"]["premium_requests"] == 8
    assert u["total"]["input_tokens"] == 8 * 1200 and u["by_role"]["planner"]["premium_requests"] == 2
    rep = hc.report()
    assert "8 premium requests" in rep and "Set `cost.premium_request_usd`" in rep
    assert all("-s" in c["argv"] for c in hc.calls())             # nothing about the calls changed
    # one machine-readable line per call, next to the logs
    run_dir = hc.repo / ".semipilot/runs" / hc.progress()["run_id"]     # (the questions call is logged under preflight-…)
    lines = [json.loads(l) for l in (run_dir / "calls.jsonl").read_text().splitlines()]
    assert len(lines) == 7 and lines[-1]["role"] == "reviewer" and lines[-1]["usage"]["premium_requests"] == 1
    assert lines[-1]["harness"] == "copilot" and lines[-1]["model"] == "fake-model-1"


def test_premium_requests_become_dollars_once_priced(hc, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_SESSION_DIR", str(hc.git_root.parent / "copilot-sessions"))
    hc.cfg["cost"]["premium_request_usd"] = 0.04
    hc.scenario()
    hc.run()
    rep = hc.report()
    assert "8 premium requests" in rep and "$0.32" in rep and "Set `cost.premium_request_usd`" not in rep


def test_copilot_without_any_usage_source_says_so(hc):
    hc.scenario()
    hc.run()                                                       # no session files, --silent: nothing reported
    u = hc.progress()["budget"]["usage"]
    assert u["total"]["calls"] == 8 and "premium_requests" not in u["total"]
    assert "reported no usage figures" in hc.report()


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_copilot_stats_block_when_not_silent(hc, monkeypatch, stream):
    monkeypatch.setenv("FAKE_AGENT_STATS", stream)
    hc.cfg["harnesses"]["copilot"]["usage"]["silent"] = False
    hc.scenario()
    _, reason = hc.run()
    assert reason == "completed"
    assert not any("-s" in c["argv"] for c in hc.calls())
    assert hc.progress()["budget"]["usage"]["total"]["premium_requests"] == 8
    # the stats never reach anything built from an agent's answer
    assert (hc.feat / "open-questions.md").read_text() == NO_QUESTIONS
    assert "Total usage est" not in hc.report()


def test_printed_stats_never_look_like_a_quota_error(hc, monkeypatch):
    """The stats block says "Premium requests"; a failing call that prints it must not be read as quota exhaustion."""
    monkeypatch.setenv("FAKE_AGENT_STATS", "stderr")
    hc.cfg["harnesses"]["copilot"]["usage"]["silent"] = False
    hc.scenario(implementer_t1=[step(exit=1, stderr="something odd happened"),
                                step(exit=1, stderr="something odd happened"),
                                step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])])
    _, reason = hc.run()
    assert reason == "completed" and hc.progress()["stop_reason"] != "quota_exhausted"


def test_usage_source_off(hc, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_SESSION_DIR", str(hc.git_root.parent / "copilot-sessions"))
    hc.cfg["harnesses"]["copilot"]["usage"]["source"] = "off"
    hc.scenario()
    hc.run()
    assert "premium_requests" not in hc.progress()["budget"]["usage"]["total"]


def test_usage_survives_a_resume(hc, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_SESSION_DIR", str(hc.git_root.parent / "copilot-sessions"))
    hc.set_spec(risk="medium")
    hc.scenario()
    hc.run()                                                       # questions, plan, 2 critics → stops for approval
    assert hc.progress()["budget"]["usage"]["total"]["premium_requests"] == 4
    hc.do(lambda: hc.loop().approve_plan())
    hc.resume()                                                    # test-writer, 2 tasks, reviewer
    assert hc.progress()["budget"]["usage"]["total"]["premium_requests"] == 8


# ---------------------------------------------------------------- spend caps
def test_premium_request_cap_stops_the_run_between_tasks(hc, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_SESSION_DIR", str(hc.git_root.parent / "copilot-sessions"))
    hc.cfg["budget"]["max_premium_requests"] = 6                   # 5 are spent before T1, T1 is the 6th
    hc.scenario()
    _, reason = hc.run()
    assert reason == "budget_exhausted"
    p = hc.progress()
    assert "max_premium_requests (6 of 6)" in p["stop_detail"]
    assert hc.task("T1")["status"] == "done" and hc.task("T2")["status"] == "pending"
    hc.cfg["budget"]["max_premium_requests"] = None
    _, reason = hc.resume()
    assert reason == "completed"


def test_cost_cap_in_dollars(tmp_path):
    from conftest import Harness
    h = Harness(tmp_path, harness="claude")                        # the fake reports $0.01 per call
    h.cfg["budget"]["max_cost_usd"] = 0.055
    h.scenario()
    _, reason = h.run()
    assert reason == "budget_exhausted" and "max_cost_usd ($0.06 of $0.06)" in h.progress()["stop_detail"]
    assert h.task("T2")["status"] == "pending"
