"""0.2.2: the fixes from the first real Copilot runs — long prompts, interrupted runs, resume from the base branch,
the approval message, capped check output, and one clear `Next:` per stop."""
import subprocess

import pytest

from conftest import FEATURE, Harness, step
from semipilot import cli
from semipilot.harness import get_harness, pointer_prompt
from semipilot.orchestrator import PreflightError, trim_output


# ------------------------------------------------------------------ long prompts (argument list too long)
def test_copilot_long_prompt_goes_to_a_file(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    hz = get_harness({**cfg, "harness": "copilot"})
    big = "x" * (200 * 1024)
    inv = hz.command("implementer", "write", big, str(tmp_path / "run" / "cli"))
    assert big not in inv.argv and inv.prompt_file
    arg = inv.argv[inv.argv.index("-p") + 1]
    assert arg == pointer_prompt(inv.prompt_file) and len(arg) < 1000
    assert open(inv.prompt_file, encoding="utf-8").read() == big
    assert "prompts" in inv.prompt_file  # next to the run's logs, git-ignored with them


def test_copilot_short_prompt_stays_on_the_command_line(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    inv = get_harness({**cfg, "harness": "copilot"}).command("planner", "read", "short", str(tmp_path / "cli"))
    assert inv.prompt_file is None and inv.argv[inv.argv.index("-p") + 1] == "short"


def test_prompt_file_grants_read_even_to_the_none_profile(tmp_path):
    from semipilot.config import load_config
    cfg = load_config(tmp_path)
    inv = get_harness({**cfg, "harness": "copilot"}).command("health", "none", "y" * 200_000, str(tmp_path / "cli"))
    assert "--allow-tool=read" in inv.argv


def test_full_run_with_a_long_prompt_completes(tmp_path):
    hs = Harness(tmp_path, harness="copilot")
    hs.cfg["harnesses"]["copilot"]["prompt_file_threshold"] = 2000  # every loop prompt is "long"
    hs.scenario()
    o, reason = hs.run()
    assert reason == "completed"
    assert all(len(c["argv"][c["argv"].index("-p") + 1]) < 1000 for c in hs.calls())


def test_a_cli_that_cannot_start_halts_cleanly(tmp_path, monkeypatch):
    hs = Harness(tmp_path, harness="copilot")
    hs.scenario()
    real = subprocess.run

    def e2big(argv, *a, **kw):
        if isinstance(argv, list) and "-p" in argv:
            raise OSError(7, "Argument list too long")
        return real(argv, *a, **kw)
    monkeypatch.setattr(subprocess, "run", e2big)
    o, reason = hs.run(skip_questions=True)
    assert reason == "agent_start_failed"
    assert "Argument list too long" in hs.progress()["stop_detail"]


# ------------------------------------------------------------------ check output
def test_trim_output_strips_colour_cuts_long_lines_and_keeps_the_end():
    text = "\n".join(["\x1b[31mred\x1b[0m"] + ["m" * 50_000] * 30 + ["FAILED tests/test_x.py::test_y"])
    out = trim_output(text, 200, 16000)
    assert "\x1b" not in out
    assert len(out.encode()) < 20_000
    assert out.endswith("FAILED tests/test_x.py::test_y")
    assert "more characters cut" in out and "earlier lines cut" in out


# ------------------------------------------------------------------ interrupted runs, resume
def halted(hs):
    """A run that stopped on an auth failure: run branch + committed checkpoint, user back on main."""
    hs.scenario(implementer_t1=[step(exit=1, stderr=hs.err["fatal"])])
    o, reason = hs.run()
    assert reason == "auth_failure"
    hs.git("checkout", "-q", "main")
    return o


@pytest.mark.parametrize("harness", ["copilot", "claude"])
def test_run_again_after_an_interruption_points_to_resume(tmp_path, harness):
    hs = Harness(tmp_path, harness=harness)
    halted(hs)
    with pytest.raises(PreflightError) as e:
        hs.run()
    msg = str(e.value)
    assert f"semipilot resume {FEATURE}" in msg and "already has a run on branch feat/calc" in msg
    assert "auth_failure" in msg
    assert "run state" not in hs.git("log", "--oneline", "main")  # nothing of the run was committed onto main


@pytest.mark.parametrize("harness", ["copilot", "claude"])
def test_resume_from_the_base_branch_finds_the_checkpoint(tmp_path, harness):
    hs = Harness(tmp_path, harness=harness)
    halted(hs)
    assert not (hs.feat / "implementation-progress.json").exists()  # it is only on the run branch
    hs.scenario()
    o, reason = hs.resume()
    assert reason == "completed"
    assert hs.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "feat/calc"


def test_resume_without_any_run_says_to_run(tmp_path):
    hs = Harness(tmp_path)
    with pytest.raises(PreflightError) as e:
        hs.resume()
    assert f"semipilot run {FEATURE}" in str(e.value)


def test_not_approved_names_the_branch_and_where_it_is_approved(tmp_path):
    hs = Harness(tmp_path)
    hs.git("checkout", "-q", "-b", "other")
    spec = hs.feat / "requirements.md"
    spec.write_text(spec.read_text().replace("status: approved", "status: draft"))
    hs.git("commit", "-qam", "draft again")
    with pytest.raises(PreflightError) as e:
        hs.run()
    msg = str(e.value)
    assert "not approved on branch other" in msg and "status: draft" in msg
    assert "approved on branch main" in msg


# ------------------------------------------------------------------ the CLI's stop output
def test_every_stop_reason_has_a_next_step():
    for reason in ("completed", "completed_with_blocked", "blocked", "plan_rejected", "auth_failure",
                   "quota_exhausted", "agent_unavailable", "agent_start_failed", "budget_exhausted",
                   "guardrail_violation", "rolled_back"):
        assert reason in cli.NEXT_STEP


def test_say_stop_prints_what_and_next(capsys):
    cli.say_stop("auth_failure", "calc", "HTTP 401 Unauthorized", ".semipilot/features/calc/report.md")
    out = capsys.readouterr().out
    assert "Stopped: the agent CLI is not logged in" in out
    assert "Next:" in out and "semipilot resume calc" in out
