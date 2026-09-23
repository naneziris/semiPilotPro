#!/usr/bin/env python3
"""Fake `copilot` CLI for tests.

Reads a scenario JSON from $FAKE_COPILOT_SCENARIO:
{
  "responses": {
    "<regex matched against the prompt>": [ {step}, {step}, ... ],   # consumed in order; last one repeats
    ...
  }
}
step = {"exit": 0, "stdout": "...", "stderr": "...",
        "actions": [{"write": "path", "content": "..."}, {"append": "path", "content": "..."},
                    {"delete": "path"}, {"assert_exists": "path"}, {"assert_contains": "path", "text": "..."}]}

Every invocation is appended to $FAKE_COPILOT_CALLS (JSON lines) with argv + prompt, so tests can assert on flags.
Exits 99 if a forbidden session flag is present (belt and braces on top of the runner's own guard).
"""
import json
import os
import re
import sys
from pathlib import Path

FORBIDDEN = ("--resume", "--continue", "--session-id")


def main() -> int:
    argv = sys.argv[1:]
    for a in argv:
        if any(a == f or a.startswith(f + "=") for f in FORBIDDEN):
            print("fake copilot: forbidden session flag", file=sys.stderr)
            return 99
    prompt = argv[argv.index("-p") + 1] if "-p" in argv else ""
    scenario = json.loads(Path(os.environ["FAKE_COPILOT_SCENARIO"]).read_text())
    counter_path = Path(os.environ["FAKE_COPILOT_SCENARIO"] + ".counters")
    counters = json.loads(counter_path.read_text()) if counter_path.exists() else {}
    calls_path = os.environ.get("FAKE_COPILOT_CALLS")
    if calls_path:
        with open(calls_path, "a") as f:
            f.write(json.dumps({"argv": argv, "prompt": prompt[:4000]}) + "\n")

    step = {"exit": 0, "stdout": "OK"}
    for pattern, steps in scenario["responses"].items():
        if re.search(pattern, prompt, re.DOTALL):
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
        elif "assert_exists" in act:
            if not Path(act["assert_exists"]).exists():
                print(f"fake copilot: expected {act['assert_exists']} to exist", file=sys.stderr)
                return 98
        elif "assert_contains" in act:
            if act["text"] not in Path(act["assert_contains"]).read_text():
                print(f"fake copilot: expected {act['assert_contains']} to contain {act['text']!r}", file=sys.stderr)
                return 98
    sys.stdout.write(step.get("stdout", ""))
    sys.stderr.write(step.get("stderr", ""))
    return int(step.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
