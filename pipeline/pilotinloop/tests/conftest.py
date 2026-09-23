import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PILOTINLOOP = HERE.parent
sys.path.insert(0, str(PILOTINLOOP))

import orchestrator as orch  # noqa: E402

FAKE = HERE / "fake_copilot.py"

REQUIREMENTS = """# Feature: calc

Add two tiny pure functions.

## Acceptance criteria
- add(a, b) returns the sum [check: test_add]
- mul(a, b) returns the product [check: test_mul]
"""

PLAN = {
    "feature": "calc",
    "tasks": [
        {"id": "T1", "title": "add function", "description": "Create calc/add.py with add(a, b).",
         "depends_on": [], "expected_files": ["calc/__init__.py", "calc/add.py"],
         "acceptance_checks": ["test_add"], "size": "S", "interfaces": ["calc.add:add(a: int, b: int) -> int"]},
        {"id": "T2", "title": "mul function", "description": "Create calc/mul.py with mul(a, b).",
         "depends_on": ["T1"], "expected_files": ["calc/mul.py"],
         "acceptance_checks": ["test_mul"], "size": "S", "interfaces": ["calc.mul:mul(a: int, b: int) -> int"]},
    ],
}

TEST_FILE_GOOD = """from calc.add import add

def test_add():
    assert add(2, 3) == 5
"""

TEST_FILE_MUL = """from calc.mul import mul

def test_mul():
    assert mul(2, 3) == 6
"""

ADD_OK = "def add(a, b):\n    return a + b\n"
ADD_BAD = "def add(a, b):\n    return a - b\n"
MUL_OK = "def mul(a, b):\n    return a * b\n"

ACCEPT = {"exit": 0, "stdout": json.dumps({"verdict": "accept", "issues": []})}


def step(exit=0, stdout="OK", stderr="", actions=None):
    return {"exit": exit, "stdout": stdout, "stderr": stderr, "actions": actions or []}


def write(path, content):
    return {"write": path, "content": content}


class Harness:
    def __init__(self, tmp_path: Path):
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        self.state = tmp_path / "state"
        self.scenario_path = tmp_path / "scenario.json"
        self.calls_path = tmp_path / "calls.jsonl"
        os.environ["FAKE_COPILOT_SCENARIO"] = str(self.scenario_path)
        os.environ["FAKE_COPILOT_CALLS"] = str(self.calls_path)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        req = self.repo / ".github" / "requirements" / "requirements.md"
        req.parent.mkdir(parents=True)
        req.write_text(REQUIREMENTS)
        (self.repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        self.cfg = orch.load_config()
        self.cfg["runner"]["command"] = f"{sys.executable} {FAKE}"
        self.cfg["runner"]["call_timeout_seconds"] = 30
        self.cfg["state_dir"] = str(self.state)
        self.cfg["infra"].update({"backoff_start_seconds": 0.01, "backoff_cap_seconds": 0.02})
        self.cfg["checks"] = [
            {"name": "build", "cmd": f"{sys.executable} -m compileall -q calc"},
            {"name": "tests", "cmd": f"{sys.executable} -m pytest -q -p no:cacheprovider {{task_tests}}"},
        ]
        self.cfg["preflight"]["auth_check_cmd"] = None
        self.sleeps = []

    def _git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def git(self, *a):
        return self._git(*a)

    def scenario(self, implementer_t1=None, implementer_t2=None, test_writer=None, planner=None, critics=None, extra=None):
        responses = {
            "questions-only mode": [step(stdout="# Open questions — calc\n\nNone.")],
            "Output \\*\\*only\\*\\* a JSON object matching": planner or [step(stdout=json.dumps(PLAN))],
            "You are the spec-critic": critics or [ACCEPT],
            "You are the plan-critic": critics or [ACCEPT],
            "You are the test-writer": test_writer or [step(actions=[write("tests/test_calc.py", TEST_FILE_GOOD), write("tests/test_mul.py", TEST_FILE_MUL)])],
            "Implement \\*\\*only task T1\\*\\*": implementer_t1 or [
                step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])],
            "Implement \\*\\*only task T2\\*\\*": implementer_t2 or [step(actions=[write("calc/mul.py", MUL_OK)])],
        }
        responses.update(extra or {})
        self.scenario_path.write_text(json.dumps({"responses": responses}))
        counters = Path(str(self.scenario_path) + ".counters")
        if counters.exists():
            counters.unlink()

    def pilotinloop(self, cfg=None):
        o = orch.PilotInLoop(self.repo, cfg or self.cfg, sleep_fn=self.sleeps.append)
        cwd = os.getcwd()
        os.chdir(self.repo)  # fake copilot writes relative paths, like the real CLI in cwd
        try:
            reason = o.pilotinloop("calc")
        finally:
            os.chdir(cwd)
        return o, reason

    def resume(self, cfg=None):
        o = orch.PilotInLoop(self.repo, cfg or self.cfg, sleep_fn=self.sleeps.append)
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            reason = o.resume()
        finally:
            os.chdir(cwd)
        return o, reason

    def progress(self):
        return json.loads((self.repo / ".github/implementation-progress.json").read_text())

    def task(self, tid):
        return next(t for t in self.progress()["tasks"] if t["id"] == tid)

    def calls(self):
        if not self.calls_path.exists():
            return []
        return [json.loads(l) for l in self.calls_path.read_text().splitlines()]

    def log(self):
        return self._git("log", "--oneline")

    def report(self):
        return next((self.repo / "reports").glob("*.md")).read_text()


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)
