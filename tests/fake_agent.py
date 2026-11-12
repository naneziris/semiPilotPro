#!/usr/bin/env python3
"""Fake agent CLI for tests — speaks both supported harness dialects.

Copilot dialect:  fake_agent.py -p "<prompt>" -s --no-ask-user ...        → plain stdout
Claude dialect:   fake_agent.py -p --output-format json ... < prompt      → one JSON result object on stdout

Reads a scenario JSON from $FAKE_AGENT_SCENARIO:
{
  "responses": {
    "<regex matched against the prompt's task part>": [ {step}, {step}, ... ],   # consumed in order; last repeats
    ...
  }
}
step = {"exit": 0, "stdout": "...", "stderr": "...",
        "actions": [{"write": "path", "content": "..."}, {"append": "path", "content": "..."},
                    {"delete": "path"}, {"git": ["checkout", "-b", "x"]},
                    {"assert_exists": "path"}, {"assert_contains": "path", "text": "..."}]}

The prompt's *task part* is the text after the "# Your task" heading when a role definition precedes it (roles mention
other modes, so matching the whole prompt would be ambiguous); otherwise the whole prompt.

Usage reporting, as the real CLIs do it:
- Copilot dialect: with $FAKE_AGENT_SESSION_DIR set, every call writes `<dir>/<id>/events.jsonl` ending in a
  `session.shutdown` event (1 premium request, 1200 in / 300 out); without `-s` it prints the stats block to the
  stream named by $FAKE_AGENT_STATS (stdout | stderr; default stdout).
- Claude dialect: the JSON result carries `total_cost_usd`, `usage` and `duration_api_ms`.

Every invocation is appended to $FAKE_AGENT_CALLS (JSON lines) with argv, dialect and prompt, so tests can assert on
flags. Exits 99 if a forbidden session flag is present (belt and braces on top of the adapters' own guard).
"""
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

STATS = """
Total usage est:        1 Premium request
API time spent:         2.5s
Total session time:     3.1s
Total code changes:     +0 -0
Breakdown by AI model:
 fake-model-1            1.2k in, 300 out, 800 cached (Est. 1 Premium request)
"""

FORBIDDEN = ("--resume", "--continue", "--session-id", "--fork-session", "--dangerously-skip-permissions")
TASK_HEADING = "\n# Your task\n"


def main() -> int:
    argv = sys.argv[1:]
    for a in argv:
        if any(a == f or a.startswith(f + "=") for f in FORBIDDEN):
            print("fake agent: forbidden session flag", file=sys.stderr)
            return 99
    claude = "--output-format" in argv
    if claude:
        prompt = sys.stdin.read()
    else:
        prompt = argv[argv.index("-p") + 1] if "-p" in argv else ""
        # a long prompt arrives as a pointer to a file (like the real CLI, the agent reads it with its read tool)
        m = re.match(r"Your full instructions for this task are in the file `([^`]+)`", prompt)
        if m:
            prompt = Path(m.group(1)).read_text(encoding="utf-8")
    task = prompt.split(TASK_HEADING, 1)[1] if TASK_HEADING in prompt else prompt
    scenario = json.loads(Path(os.environ["FAKE_AGENT_SCENARIO"]).read_text())
    counter_path = Path(os.environ["FAKE_AGENT_SCENARIO"] + ".counters")
    counters = json.loads(counter_path.read_text()) if counter_path.exists() else {}
    calls_path = os.environ.get("FAKE_AGENT_CALLS")
    if calls_path:
        with open(calls_path, "a") as f:
            f.write(json.dumps({"argv": argv, "dialect": "claude" if claude else "copilot", "prompt": prompt[:12000],
                                "stdin": claude}) + "\n")

    step = {"exit": 0, "stdout": "OK"}
    for pattern, steps in scenario["responses"].items():
        if re.search(pattern, task, re.DOTALL):
            i = counters.get(pattern, 0)
            step = steps[min(i, len(steps) - 1)]
            counters[pattern] = i + 1
            break
    counter_path.write_text(json.dumps(counters))

    for act in step.get("actions", []):
        if "write" in act:
            p = Path(act["write"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(act["content"])
        elif "append" in act:
            with open(act["append"], "a") as f:
                f.write(act["content"])
        elif "delete" in act:
            Path(act["delete"]).unlink(missing_ok=True)
        elif "git" in act:
            subprocess.run(["git", *act["git"]], capture_output=True)
        elif "assert_exists" in act:
            if not Path(act["assert_exists"]).exists():
                print(f"fake agent: expected {act['assert_exists']} to exist", file=sys.stderr)
                return 98
        elif "assert_contains" in act:
            if act["text"] not in Path(act["assert_contains"]).read_text():
                print(f"fake agent: expected {act['assert_contains']} to contain {act['text']!r}", file=sys.stderr)
                return 98
    code = int(step.get("exit", 0))
    out, err = step.get("stdout", ""), step.get("stderr", "")
    if claude:
        # Claude Code prints one JSON result object; API/auth errors land in `result` with is_error set.
        result = out if code == 0 else (out + "\n" + err).strip()
        obj = {"type": "result", "subtype": "success" if code == 0 else "error_during_execution",
               "is_error": code != 0, "result": result, "session_id": "fake", "total_cost_usd": 0.01, "num_turns": 1,
               "duration_api_ms": 2500, "usage": {"input_tokens": 400, "cache_creation_input_tokens": 800,
                                                  "cache_read_input_tokens": 5000, "output_tokens": 300},
               "ttft_ms": 502, "process_rss_mib_result": 429}  # telemetry numbers that must never look like errors
        obj.update(step.get("claude_json") or {})            # e.g. {"subtype": "error_max_turns"} or api_error_status
        sys.stdout.write(json.dumps(obj))
        sys.stderr.write("" if code == 0 else err)
    else:
        sys.stdout.write(out)
        sys.stderr.write(err)
        session_root = os.environ.get("FAKE_AGENT_SESSION_DIR")
        if session_root:
            d = Path(session_root) / uuid.uuid4().hex
            d.mkdir(parents=True, exist_ok=True)
            events = [{"type": "session.start", "data": {"context": {"cwd": os.environ.get("FAKE_AGENT_SESSION_CWD") or os.getcwd()}}},
                      {"type": "assistant.message", "data": {"content": "..."}},
                      {"type": "session.shutdown", "data": {
                          "totalPremiumRequests": 1, "totalApiDurationMs": 2500,
                          "modelMetrics": {"fake-model-1": {"requests": {"count": 1, "cost": 1},
                                                            "usage": {"inputTokens": 1200, "outputTokens": 300,
                                                                      "cacheReadTokens": 800, "cacheWriteTokens": 0}}}}}]
            (d / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        if "-s" not in argv and "--silent" not in argv:
            (sys.stderr if os.environ.get("FAKE_AGENT_STATS") == "stderr" else sys.stdout).write(STATS)
    return code


if __name__ == "__main__":
    sys.exit(main())
