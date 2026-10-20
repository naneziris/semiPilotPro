import json

import pytest

from semipilot.harness import ClaudeCodeHarness, CopilotHarness, get_harness
from semipilot.runner import (FATAL, OK, QUOTA, TASK_FAILURE, TRANSIENT, UNKNOWN, CallResult, ForbiddenFlagError,
                              HaltRun, Runner, classify)


def mk_runner(h, tmp_path, **infra):
    h.cfg["infra"].update(infra)
    return Runner(h.cfg, tmp_path / "logs", sleep_fn=h.sleeps.append, cwd=h.repo)


def res(exit_code, text="", timed_out=False, meta=None):
    return CallResult(exit_code=exit_code, stdout="", stderr=text, duration_s=0.1, timed_out=timed_out, meta=meta or {})


# ---------------------------------------------------------------- fresh session guarantee (both harnesses)
def test_runner_never_passes_resume_or_continue(h, tmp_path):
    r = mk_runner(h, tmp_path)
    inv = r.build("implementer", "do it")
    if h.harness == "copilot":
        assert inv.argv[inv.argv.index("-p") + 1] == "do it" and inv.stdin is None
    else:
        assert inv.stdin == "do it" and "--no-session-persistence" in inv.argv
    with pytest.raises(ForbiddenFlagError):
        r.build_command("implementer", "x", extra=["--continue"])


@pytest.mark.parametrize("flag", ["--resume", "--continue", "--session-id"])
def test_runner_refuses_forbidden_flags_from_config(h, tmp_path, flag):
    h.cfg["runner"]["extra_flags"] = [flag]
    with pytest.raises(ForbiddenFlagError):
        mk_runner(h, tmp_path).build_command("implementer", "x")


def test_runner_refuses_forbidden_flags_via_extra(h, tmp_path):
    with pytest.raises(ForbiddenFlagError):
        mk_runner(h, tmp_path).build_command("implementer", "x", extra=["--session-id=abc"])


def test_permission_bypass_flags_are_refused(h, tmp_path):
    bypass = "--allow-all-tools" if h.harness == "copilot" else "--dangerously-skip-permissions"
    h.cfg["runner"]["extra_flags"] = [bypass]
    with pytest.raises(ForbiddenFlagError):
        mk_runner(h, tmp_path).build_command("implementer", "x")


def test_prompt_text_that_looks_like_a_flag_is_not_refused(h, tmp_path):
    r = mk_runner(h, tmp_path)
    assert r.build("implementer", "--resume")  # the prompt itself is never inspected as a flag


# ---------------------------------------------------------------- permission profiles
def test_copilot_profiles_and_deny_list(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    cmd = get_harness({**cfg, "harness": "copilot"}).command("implementer", "write", "x", "logs").argv
    assert "--agent" not in cmd  # role prompts are inlined; no custom agent files
    assert "--allow-tool=write" in cmd and "--allow-tool=shell" in cmd
    assert "--deny-tool=shell(git push)" in cmd and "--deny-tool=shell(git commit)" in cmd and "--deny-tool=url" in cmd
    read = get_harness({**cfg, "harness": "copilot"}).command("planner", "read", "x", "logs").argv
    assert "--allow-tool=read" in read and "--allow-tool=write" not in read and "--allow-tool=shell" not in read
    assert "--deny-tool=shell(git push)" in read


def test_claude_profiles_and_deny_list(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    hz = get_harness({**cfg, "harness": "claude"})
    w = hz.command("implementer", "write", "x", "logs").argv
    assert w[w.index("--permission-mode") + 1] == "dontAsk"  # nothing can wait for a human
    allowed = w[w.index("--allowedTools") + 1:w.index("--disallowedTools")]
    denied = w[w.index("--disallowedTools") + 1:]
    assert {"Edit", "Write", "Bash", "Read"} <= set(allowed)
    assert "Bash(git push *)" in denied and "WebFetch" in denied and "Bash(git commit *)" in denied
    r = hz.command("plan-critic", "read", "x", "logs").argv
    allowed = r[r.index("--allowedTools") + 1:r.index("--disallowedTools")]
    assert "Read" in allowed and not ({"Edit", "Write", "Bash", "NotebookEdit"} & set(allowed))
    none = hz.command("health", "none", "x", "logs").argv
    assert "--allowedTools" not in none


def test_claude_bypass_permission_mode_is_refused(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    cfg["harnesses"]["claude"]["permission_mode"]["write"] = "bypassPermissions"
    with pytest.raises(ForbiddenFlagError):
        get_harness({**cfg, "harness": "claude"}).command("implementer", "write", "x", "logs")


def test_role_profiles_come_from_config(h, tmp_path):
    r = mk_runner(h, tmp_path)
    write_flag = "--allow-tool=write" if h.harness == "copilot" else "Edit"
    assert write_flag in r.build_command("implementer", "x")
    assert write_flag not in r.build_command("spec-critic", "x")
    h.cfg["roles"]["spec-critic"] = "write"
    assert write_flag in mk_runner(h, tmp_path).build_command("spec-critic", "x")


def test_unknown_harness_is_a_clear_error(tmp_path):
    from semipilot.config import load_config
    from semipilot.harness import UnknownHarnessError
    with pytest.raises(UnknownHarnessError) as e:
        get_harness({**load_config(tmp_path), "harness": "vim"})
    assert "copilot" in str(e.value) and "claude" in str(e.value)


def test_harness_aliases(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    assert isinstance(get_harness({**cfg, "harness": "claude-code"}), ClaudeCodeHarness)
    assert isinstance(get_harness({**cfg, "harness": "Copilot-CLI"}), CopilotHarness)


# ---------------------------------------------------------------- Claude Code JSON output
def test_claude_response_parses_result_and_cost():
    hz = ClaudeCodeHarness({})
    text, meta = hz.response(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                         "result": '{"verdict": "accept", "issues": []}', "total_cost_usd": 0.42,
                                         "session_id": "s", "permission_denials": [{"tool": "Edit"}]}))
    assert Runner.extract_json(text) == {"verdict": "accept", "issues": []}
    assert meta["total_cost_usd"] == 0.42 and meta["is_error"] is False and meta["permission_denials"] == 1


def test_claude_response_tolerates_noise_and_non_json():
    hz = ClaudeCodeHarness({})
    assert hz.response('warning: x\n{"result": "hi"}')[0] == "hi"
    assert hz.response("plain text")[0] == "plain text"


def test_claude_is_error_with_zero_exit_is_classified(tmp_path):
    from semipilot.config import load_config
    pats = get_harness({**load_config(tmp_path), "harness": "claude"}).failure_patterns()
    r = CallResult(exit_code=0, stdout="", stderr="", duration_s=1, text="Credit balance is too low", meta={"is_error": True})
    assert classify(r, pats) == QUOTA
    r = CallResult(exit_code=0, stdout="", stderr="", duration_s=1, text="Reached max turns", meta={"is_error": True})
    assert classify(r, pats) == TASK_FAILURE


# ---------------------------------------------------------------- classification
COPILOT_CASES = [
    (0, "", OK),
    (1, "Error: request failed with status 502 Bad Gateway", TRANSIENT),
    (1, "429 Too Many Requests", TRANSIENT),
    (1, "FetchError: ECONNRESET", TRANSIENT),
    (1, "HTTP 401 Unauthorized", FATAL),
    (1, "error: token expired, please run copilot login", FATAL),
    (1, "You have exhausted your premium request quota", QUOTA),
    (1, "session limit reached", QUOTA),
    (1, "something completely new happened", UNKNOWN),
    (1, "", UNKNOWN),
]
CLAUDE_CASES = [
    (0, "", OK),
    (1, "API Error: Request rejected (429) · this may be a temporary capacity issue", TRANSIENT),
    (1, "API Error: Repeated 529 Overloaded errors", TRANSIENT),
    (1, "API Error: 500 Internal server error", TRANSIENT),
    (1, "Not logged in · Please run /login", FATAL),
    (1, "Invalid API key · Fix external API key", FATAL),
    (1, "Login expired · Please run /login", FATAL),
    (1, "You've hit your weekly limit · resets Mon 9am", QUOTA),
    (1, "Credit balance is too low", QUOTA),
    (1, "something completely new happened", UNKNOWN),
]


@pytest.mark.parametrize("harness,code,text,expected",
                         [("copilot", *c) for c in COPILOT_CASES] + [("claude", *c) for c in CLAUDE_CASES])
def test_classify(tmp_path, harness, code, text, expected):
    from semipilot.config import load_config
    pats = get_harness({**load_config(tmp_path), "harness": harness}).failure_patterns()
    assert classify(res(code, text), pats) == expected


def test_user_failure_patterns_extend_the_harness_list(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    cfg["failure_patterns"] = {"transient": ["upstream connect error"]}
    pats = get_harness({**cfg, "harness": "claude"}).failure_patterns()
    assert classify(res(1, "upstream connect error or disconnect"), pats) == TRANSIENT
    assert classify(res(1, "Not logged in"), pats) == FATAL  # own patterns still there


def test_timeout_is_task_failure(h):
    assert classify(res(-9, "", timed_out=True), {}) == TASK_FAILURE


def test_missing_executable_is_reported_not_raised(h, tmp_path):
    h.cfg["runner"]["command"] = "definitely-not-an-agent-cli-xyz"
    out = mk_runner(h, tmp_path).invoke("health", "hi", "health")
    assert out.exit_code == 127 and "command not found" in out.stderr


# ---------------------------------------------------------------- retry policy (monkeypatched invoke)
def scripted(r, kinds):
    seq = list(kinds)

    def fake_invoke(role, prompt, label, extra=None):
        k = seq.pop(0)
        out = CallResult(exit_code=0 if k == OK else 1, stdout="", stderr=k, duration_s=0)
        out.kind = k
        return out

    r.invoke = fake_invoke
    return r


def test_transient_then_ok_does_not_raise_and_counts_outage(h, tmp_path):
    r = scripted(mk_runner(h, tmp_path), [TRANSIENT, TRANSIENT, OK])
    out = r.run("implementer", "p", "T1-attempt1")
    assert out.kind == OK
    assert r.outage.transient_count == 2
    assert len(h.sleeps) == 2 and h.sleeps[1] >= h.sleeps[0] * 0.8  # backoff grows


def test_fatal_halts_immediately(h, tmp_path):
    r = scripted(mk_runner(h, tmp_path), [FATAL, OK])
    with pytest.raises(HaltRun) as e:
        r.run("implementer", "p", "x")
    assert e.value.reason == "auth_failure"
    assert h.sleeps == []


def test_quota_halts_immediately_not_backoff(h, tmp_path):
    r = scripted(mk_runner(h, tmp_path), [QUOTA, OK])
    with pytest.raises(HaltRun) as e:
        r.run("implementer", "p", "x")
    assert e.value.reason == "quota_exhausted"
    assert h.sleeps == []


def test_breaker_trips_on_sustained_outage(h, tmp_path):
    r = scripted(mk_runner(h, tmp_path, max_outage_seconds=0.025, max_total_outage_seconds=1000), [TRANSIENT] * 50)
    with pytest.raises(HaltRun) as e:
        r.run("implementer", "p", "x")
    assert e.value.reason == "agent_unavailable"
    assert r.outage.breaker_tripped


def test_unknown_treated_as_transient_once_then_task_failure(h, tmp_path):
    r = scripted(mk_runner(h, tmp_path), [UNKNOWN, UNKNOWN])
    out = r.run("implementer", "p", "x")
    assert out.kind == TASK_FAILURE
    assert r.outage.transient_count == 1


def test_reset_tree_called_before_transient_retry(h, tmp_path):
    calls = []
    r = scripted(mk_runner(h, tmp_path), [TRANSIENT, OK])
    r.reset_tree = lambda: calls.append(1)
    r.run("implementer", "p", "x")
    assert calls == [1]


def test_extract_json_tolerates_fences_and_chatter():
    assert Runner.extract_json('Sure!\n```json\n{"a": 1}\n```\nDone.') == {"a": 1}
    assert Runner.extract_json('prefix {"verdict": "accept", "issues": []} suffix') == {"verdict": "accept", "issues": []}
    assert Runner.extract_json("no json here") is None
    assert Runner.extract_json("[1, 2]") is None


def test_claude_ignores_settings_files_and_denies_the_state_dir(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    argv = get_harness({**cfg, "harness": "claude"}).command("plan-critic", "read", "x", "logs").argv
    assert argv[argv.index("--setting-sources") + 1] == ""  # repo/user allow rules cannot widen the profile
    assert "Read(~/.semipilot/state/**)" in argv and "Edit(~/.semipilot/state/**)" in argv
    cfg["state_dir"] = "/srv/sp-state"
    argv = get_harness({**cfg, "harness": "claude"}).command("implementer", "write", "x", "logs").argv
    assert "Read(//srv/sp-state/**)" in argv


def test_claude_telemetry_numbers_never_look_like_http_errors(tmp_path):
    from semipilot.config import load_config
    hz = get_harness({**load_config(tmp_path), "harness": "claude"})
    raw = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": "tests still failing", "ttft_ms": 503, "process_rss_mib_result": 429})
    text, meta = hz.response(raw)
    r = CallResult(exit_code=1, stdout=raw, stderr="", duration_s=1, text=text, meta=meta)
    assert classify(r, hz.failure_patterns(), hz) == UNKNOWN  # not TRANSIENT because of 503/429 in telemetry
    for meta2, kind in [({"subtype": "error_max_turns", "is_error": True}, TASK_FAILURE),
                        ({"subtype": "error_max_budget_usd", "is_error": True}, TASK_FAILURE),
                        ({"is_error": True, "api_error_status": 529}, TRANSIENT),
                        ({"is_error": True, "api_error_status": 401}, FATAL)]:
        assert classify(CallResult(exit_code=1, stdout="{}", stderr="", duration_s=1, text="", meta=meta2),
                        hz.failure_patterns(), hz) == kind
