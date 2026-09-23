import pytest

from runner import (FATAL, OK, QUOTA, TASK_FAILURE, TRANSIENT, UNKNOWN, CallResult, CopilotRunner,
                    ForbiddenFlagError, HaltRun, classify)


def mk_runner(h, tmp_path, **infra):
    h.cfg["infra"].update(infra)
    return CopilotRunner(h.cfg, tmp_path / "logs", sleep_fn=h.sleeps.append, cwd=h.repo)


def res(exit_code, text="", timed_out=False):
    return CallResult(exit_code=exit_code, stdout="", stderr=text, duration_s=0.1, timed_out=timed_out)


# ---------------------------------------------------------------- fresh session guarantee
def test_runner_never_passes_resume_or_continue(h, tmp_path):
    r = mk_runner(h, tmp_path)
    cmd = r.build_command("implementer", "do it")
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "do it"
    for bad in ("--resume", "--continue", "--session-id"):
        assert not any(a == bad or a.startswith(bad + "=") for a in cmd)
    assert "--no-ask-user" in cmd and "-s" in cmd


@pytest.mark.parametrize("flag", ["--resume", "--resume=abc", "--continue", "--session-id=xyz", "-r"])
def test_runner_refuses_forbidden_flags_from_config(h, tmp_path, flag):
    h.cfg["runner"]["extra_flags"] = [flag]
    r = mk_runner(h, tmp_path)
    with pytest.raises(ForbiddenFlagError):
        r.build_command("implementer", "x")


def test_runner_refuses_forbidden_flags_via_extra(h, tmp_path):
    r = mk_runner(h, tmp_path)
    with pytest.raises(ForbiddenFlagError):
        r.build_command("implementer", "x", extra=["--continue"])


def test_command_carries_role_permissions_and_deny_list(h, tmp_path):
    r = mk_runner(h, tmp_path)
    cmd = r.build_command("implementer", "x")
    assert "--agent" not in cmd  # implementer has no custom agent in defaults
    assert "--allow-tool=write" in cmd
    assert "--deny-tool=shell(git push)" in cmd
    cmd = r.build_command("planner", "x")
    assert "--agent" in cmd and cmd[cmd.index("--agent") + 1] == "pilotinloop-planner"
    assert "--allow-tool=write" not in cmd


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("code,text,expected", [
    (0, "", OK),
    (1, "Error: request failed with status 502 Bad Gateway", TRANSIENT),
    (1, "429 Too Many Requests", TRANSIENT),
    (1, "FetchError: ECONNRESET", TRANSIENT),
    (1, "HTTP 401 Unauthorized", FATAL),
    (1, "error: token expired, please run copilot login", FATAL),
    (1, "You have exhausted your premium request quota", QUOTA),
    (1, "session limit reached", QUOTA),
    (1, "something completely new happened", UNKNOWN),
    (1, "", TASK_FAILURE if False else UNKNOWN),
])
def test_classify(h, code, text, expected):
    assert classify(res(code, text), h.cfg["failure_patterns"]) == expected


def test_timeout_is_task_failure(h):
    assert classify(res(-9, "", timed_out=True), h.cfg["failure_patterns"]) == TASK_FAILURE


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
    assert e.value.reason == "copilot_unavailable"
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
    assert CopilotRunner.extract_json('Sure!\n```json\n{"a": 1}\n```\nDone.') == {"a": 1}
    assert CopilotRunner.extract_json('prefix {"verdict": "accept", "issues": []} suffix') == {"verdict": "accept", "issues": []}
    assert CopilotRunner.extract_json("no json here") is None
