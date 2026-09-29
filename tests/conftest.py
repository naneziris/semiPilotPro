import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from semipilot import orchestrator as orch
from semipilot.config import load_config

HERE = Path(__file__).resolve().parent
FAKE = HERE / "fake_copilot.py"
FEATURE = "calc"

SPEC = """---
feature: calc
status: approved
---
# Requirement: calc

Add two tiny pure functions.

## Acceptance criteria
- add(a, b) returns the sum [check: test_add]
- mul(a, b) returns the product [check: test_mul]
"""

NO_QUESTIONS = "# Open questions — calc\n\nNone — the spec is complete enough to plan.\n"

QUESTIONS = """# Open questions — calc

## Q1 — Integer or float?
- Question: Should add() accept floats?
- Why it matters: changes the type hints and the tests
- Recommended default: ints only
- Answer:
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

TEST_FILE_GOOD = "from calc.add import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
TEST_FILE_MUL = "from calc.mul import mul\n\ndef test_mul():\n    assert mul(2, 3) == 6\n"
ADD_OK = "def add(a, b):\n    return a + b\n"
ADD_BAD = "def add(a, b):\n    return a - b\n"
MUL_OK = "def mul(a, b):\n    return a * b\n"
ACCEPT = {"exit": 0, "stdout": json.dumps({"verdict": "accept", "issues": []})}


def step(exit=0, stdout="OK", stderr="", actions=None):
    return {"exit": exit, "stdout": stdout, "stderr": stderr, "actions": actions or []}


def write(path, content):
    return {"write": path, "content": content}


class Harness:
    def __init__(self, tmp_path: Path, subdir: str = ""):
        # subdir="apps/api": the project is a subfolder of the git repository (monorepo layout)
        self.git_root = tmp_path / "repo"
        self.repo = self.git_root / subdir if subdir else self.git_root
        self.repo.mkdir(parents=True)
        self.state = tmp_path / "state"
        self.scenario_path = tmp_path / "scenario.json"
        self.calls_path = tmp_path / "calls.jsonl"
        os.environ["FAKE_COPILOT_SCENARIO"] = str(self.scenario_path)
        os.environ["FAKE_COPILOT_CALLS"] = str(self.calls_path)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        self.feat = self.repo / ".semipilot" / "features" / FEATURE
        self.feat.mkdir(parents=True)
        (self.feat / "requirements.md").write_text(SPEC)
        (self.repo / ".semipilot" / ".gitignore").write_text("runs/\nlast-run\n")
        (self.git_root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        self.cfg = load_config(self.repo)
        self.cfg["runner"]["command"] = f"{sys.executable} {FAKE}"
        self.cfg["runner"]["call_timeout_seconds"] = 30
        self.cfg["state_dir"] = str(self.state)
        self.cfg["infra"].update({"backoff_start_seconds": 0.01, "backoff_cap_seconds": 0.02})
        self.cfg["checks"] = [
            {"name": "build", "cmd": f"{sys.executable} -m compileall -q calc"},
            {"name": "tests", "cmd": f"{sys.executable} -m pytest -q -p no:cacheprovider {{task_tests}}"},
        ]
        self.sleeps = []

    def _git(self, *a):
        return subprocess.run(["git", *a], cwd=self.git_root, capture_output=True, text=True, check=True).stdout

    def git(self, *a):
        return self._git(*a)

    def scenario(self, implementer_t1=None, implementer_t2=None, test_writer=None, planner=None, critics=None,
                 questions=None, extra=None):
        responses = {
            "questions-only mode": questions or [step(stdout=NO_QUESTIONS)],
            "Output \\*\\*only\\*\\* a JSON object matching": planner or [step(stdout=json.dumps(PLAN))],
            "You are the spec-critic": critics or [ACCEPT],
            "You are the plan-critic": critics or [ACCEPT],
            "You are the test-writer": test_writer or [step(actions=[write("tests/test_calc.py", TEST_FILE_GOOD), write("tests/test_mul.py", TEST_FILE_MUL)])],
            "Implement \\*\\*only task T1\\*\\*": implementer_t1 or [step(actions=[write("calc/__init__.py", ""), write("calc/add.py", ADD_OK)])],
            "Implement \\*\\*only task T2\\*\\*": implementer_t2 or [step(actions=[write("calc/mul.py", MUL_OK)])],
        }
        responses.update(extra or {})
        self.scenario_path.write_text(json.dumps({"responses": responses}))
        counters = Path(str(self.scenario_path) + ".counters")
        if counters.exists():
            counters.unlink()

    def loop(self, cfg=None):
        return orch.Loop(self.repo, cfg or self.cfg, FEATURE, sleep_fn=self.sleeps.append)

    def _in_repo(self, fn):
        cwd = os.getcwd()
        os.chdir(self.repo)  # the fake copilot writes relative paths, like the real CLI in cwd
        try:
            return fn()
        finally:
            os.chdir(cwd)

    def run(self, cfg=None, **kw):
        o = self.loop(cfg)
        return o, self._in_repo(lambda: o.run(**kw))

    def resume(self, cfg=None):
        o = self.loop(cfg)
        return o, self._in_repo(lambda: o.resume())

    def progress(self):
        return json.loads((self.feat / "implementation-progress.json").read_text())

    def task(self, tid):
        return next(t for t in self.progress()["tasks"] if t["id"] == tid)

    def calls(self):
        if not self.calls_path.exists():
            return []
        return [json.loads(l) for l in self.calls_path.read_text().splitlines()]

    def log(self):
        return self._git("log", "--oneline")

    def report(self):
        return (self.feat / "report.md").read_text()


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


@pytest.fixture
def h_sub(tmp_path):
    """Same, with the project in apps/api/ of a monorepo whose git root has a sibling app."""
    hs = Harness(tmp_path, subdir="apps/api")
    (hs.git_root / "apps" / "web").mkdir(parents=True)
    (hs.git_root / "apps" / "web" / "index.js").write_text("// sibling app\n")
    hs._git("add", "-A")
    hs._git("commit", "-q", "-m", "sibling app")
    return hs
