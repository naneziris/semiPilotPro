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

Every invocation is appended to $FAKE_AGENT_CALLS (JSON lines) with argv, dialect and prompt, so tests can assert on
flags. Exits 99 if a forbidden session flag is present (belt and braces on top of the adapters' own guard).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

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
               "ttft_ms": 502, "process_rss_mib_result": 429}  # telemetry numbers that must never look like errors
        obj.update(step.get("claude_json") or {})            # e.g. {"subtype": "error_max_turns"} or api_error_status
        sys.stdout.write(json.dumps(obj))
        sys.stderr.write("" if code == 0 else err)
    else:
        sys.stdout.write(out)
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
