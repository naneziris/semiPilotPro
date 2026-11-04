"""The semipilot loop: plan → critique → locked tests → implement task by task → checks → report.

The orchestrator owns the loop. The agent never decides that work is done: done == all configured checks pass.
Humans sit at the front (requirements, Gate 1 approval, answered questions) and at the back (report review).

Layout inside a repo (see config.Layout):
    .semipilot/config.yaml                 the only file a user edits
    .semipilot/features/<slug>/requirements.md        written by the semipilot-refine skill, approved after the
                                                      semipilot-spec-critic skill (status: approved) — the human gate
    .semipilot/features/<slug>/open-questions.md      planner's questions, answered inline by the human
    .semipilot/features/<slug>/implementation-plan.md the accepted plan, rendered for humans and for semipilot-scribe
    .semipilot/features/<slug>/decisions.md           assumptions the loop made (read these first)
    .semipilot/features/<slug>/rejection-log.md       critic rejections
    .semipilot/features/<slug>/report.md              the report
    .semipilot/features/<slug>/implementation-progress.json   checkpoint (resume / rollback)
    .semipilot/runs/<run_id>/                         per-call logs (untracked)
The manual pipeline's single `.github/requirements/` folder is used as-is when it exists (legacy layout).
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Optional

from .config import INSTRUCTION_CANDIDATES, Layout, instructions_file, kb_commands, knowledge_layer_present
from .harness import UnknownHarnessError, get_harness
from .runner import AGENT_UNAVAILABLE, OK, HaltRun, Runner

LEGACY_AGENT_UNAVAILABLE = "copilot_unavailable"  # stop reason written by v0.1
ROLE_FOR = {"planner-questions": "planner", "planner-plan": "planner", "plan-fidelity-critic": "plan-fidelity-critic",
            "plan-critic": "plan-critic"}
TASK_HEADING = "# Your task"


class PreflightError(Exception):
    pass


class NeedsAnswers(Exception):
    """Raised when the planner has questions the human must answer before the run can start."""

    def __init__(self, path: Path, count: int):
        super().__init__(f"{count} open question(s) in {path}")
        self.path = path
        self.count = count


def state_dir(cfg: dict, repo: Path, run_id: str) -> Path:
    base = Path(os.path.expandvars(os.path.expanduser(cfg.get("state_dir", "~/.semipilot/state"))))
    d = base / repo.name / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================== git
class Git:
    """git, run from the project root. The project may be a subfolder of the repository (monorepo):
    every path in and out of this class is relative to the project, never to the git root."""

    def __init__(self, repo: Path):
        self.repo = Path(repo)
        self._prefix: Optional[str] = None

    @property
    def prefix(self) -> str:
        """Path of the project inside the repository ("" when they coincide, else e.g. "apps/api/")."""
        if self._prefix is None:
            self._prefix = self.run("rev-parse", "--show-prefix").strip()
        return self._prefix

    def status_paths(self) -> list[str]:
        """Uncommitted paths (whole repository), relative to the project: `../x` for anything outside it."""
        out = []
        for l in self.run("status", "--porcelain").splitlines():
            if not l.strip():
                continue
            path = l[3:].split(" -> ")[-1]
            out.append(path[len(self.prefix):] if path.startswith(self.prefix) else os.path.relpath(path, self.prefix or "."))
        return out

    def run(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD").strip()

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").strip()

    def is_dirty(self) -> bool:
        return bool(self.run("status", "--porcelain").strip())

    def branch_exists(self, name: str) -> bool:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", name], cwd=self.repo,
                              capture_output=True).returncode == 0

    def create_branch(self, name: str) -> None:
        self.run("checkout", "-q", "-b", name)

    def show_file(self, ref: str, path: str) -> Optional[str]:
        """A project file's content at `ref`, or None when it does not exist there."""
        r = subprocess.run(["git", "show", f"{ref}:{self.prefix}{path}"], cwd=self.repo, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def local_branches(self, limit: int = 100) -> list[str]:
        """Local branches, most recently committed first."""
        out = self.run("for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", "refs/heads", check=False)
        return [b for b in out.splitlines() if b.strip()][:limit]

    def checkout(self, name: str) -> None:
        self.run("checkout", "-q", name)

    def changed_files(self, base: str) -> list[str]:
        tracked = self.run("diff", "--name-only", "--relative", base).splitlines()
        untracked = self.run("ls-files", "--others", "--exclude-standard").splitlines()
        return sorted(set(f for f in tracked + untracked if f))

    def diff_lines(self, base: str, paths: Optional[list[str]] = None, exclude: Optional[list[str]] = None) -> tuple[int, int]:
        self.run("add", "-N", "--", ".")
        args = ["diff", "--numstat", "--relative", base]
        if paths or exclude:
            args += ["--", *(paths or ["."]), *[f":(exclude){e.rstrip('/')}" for e in (exclude or [])]]
        out = self.run(*args)
        self.run("reset", "-q", "--", ".")
        add = rem = 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                add += int(parts[0])
                rem += int(parts[1])
        return add, rem

    def reset_hard(self, sha: str, preserve: Optional[list[str]] = None) -> list[str]:
        preserve = preserve or []
        discarded = [f for f in self.changed_files(sha) if not any(f == m or f.startswith(m) for m in preserve)]
        saved: dict[str, bytes] = {}
        for m in preserve:
            root = self.repo / m.rstrip("/")
            if root.is_file():
                saved[m] = root.read_bytes()
            elif root.is_dir():
                for p in root.rglob("*"):
                    if p.is_file():
                        saved[str(p.relative_to(self.repo))] = p.read_bytes()
        self.run("reset", "-q", "--hard", sha)
        self.run("clean", "-fdq", *[a for m in preserve for a in ("-e", m.rstrip("/"))])
        for m, data in saved.items():
            (self.repo / m).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / m).write_bytes(data)
        return discarded

    def restore_paths(self, sha: str, paths: list[str]) -> None:
        for p in paths:
            if subprocess.run(["git", "cat-file", "-e", f"{sha}:{self.prefix}{p}"], cwd=self.repo, capture_output=True).returncode == 0:
                self.run("checkout", sha, "--", p)
            else:
                (self.repo / p).unlink(missing_ok=True)

    def commit(self, message: str, exclude: list[str]) -> str:
        self.run("add", "-A", "--", ".")
        existing = [e for e in exclude if (self.repo / e.rstrip("/")).exists()]
        if existing:
            self.run("reset", "-q", "--", *[e.rstrip("/") for e in existing])
        if not self.run("diff", "--cached", "--name-only").strip():
            return self.head()
        self.run("commit", "-q", "--no-verify", "-m", message)
        return self.head()

    def revert(self, sha: str) -> bool:
        # `git revert` cannot skip hooks, so revert without committing and commit with --no-verify (the project's
        # pre-commit hook may reject intermediate states the loop is undoing; CI still checks the branch).
        subject = self.run("log", "-1", "--format=%s", sha).strip()
        r = subprocess.run(["git", "revert", "--no-edit", "--no-commit", sha], cwd=self.repo, capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "revert", "--abort"], cwd=self.repo, capture_output=True)
            return False
        self.run("commit", "-q", "--no-verify", "-m", f'Revert "{subject}"\n\nThis reverts commit {sha}.')
        return True

    def stat_between(self, a: str, b: str) -> dict:
        out = self.run("diff", "--numstat", "--relative", a, b)
        files, add, rem = 0, 0, 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].isdigit():
                files += 1
                add += int(parts[0])
                rem += int(parts[1])
        return {"files": files, "added": add, "removed": rem}


# =============================================================================== plan validation
def load_schema() -> dict:
    return json.loads(resources.files("semipilot").joinpath("plan.schema.json").read_text(encoding="utf-8"))


def validate_plan(plan: dict, cfg: dict, criteria: Optional[list[dict]] = None) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator  # jsonschema >= 4.0
    except (ImportError, AttributeError):  # not installed, or too old (e.g. 3.x shipped with an OS)
        validator = None
    if validator is not None:
        for e in validator(load_schema()).iter_errors(plan):
            errors.append(f"schema: {'/'.join(str(p) for p in e.absolute_path)}: {e.message}")
    else:
        if not isinstance(plan.get("tasks"), list) or not plan.get("feature"):
            errors.append("schema: plan must have 'feature' and 'tasks'")
    if errors:
        return errors
    g = cfg["guardrails"]
    tasks = plan["tasks"]
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate task ids")
    idset = set(ids)
    for t in tasks:
        if len(t["expected_files"]) > g["max_expected_files_per_task"]:
            errors.append(f"{t['id']}: {len(t['expected_files'])} expected_files > max {g['max_expected_files_per_task']}; split it")
        for d in t["depends_on"]:
            if d not in idset:
                errors.append(f"{t['id']}: depends on unknown task {d}")
            if d == t["id"]:
                errors.append(f"{t['id']}: depends on itself")
    try:
        topo_sort(tasks)
    except ValueError as e:
        errors.append(str(e))
    if criteria:
        refs = {c["ref"] for c in criteria}
        covered = {c for t in tasks for c in t["acceptance_checks"]}
        for ref in sorted(refs - covered):
            errors.append(f"acceptance criterion '{ref}' is not covered by any task")
        for t in tasks:
            for c in t["acceptance_checks"]:
                if c not in refs:
                    errors.append(f"{t['id']}: acceptance_check '{c}' does not match any tagged criterion in requirements.md")
    return errors


def topo_sort(tasks: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in tasks}
    seen, out, stack = set(), [], set()

    def visit(t: dict) -> None:
        if t["id"] in seen:
            return
        if t["id"] in stack:
            raise ValueError(f"dependency cycle involving {t['id']}")
        stack.add(t["id"])
        for d in t["depends_on"]:
            if d in by_id:
                visit(by_id[d])
        stack.discard(t["id"])
        seen.add(t["id"])
        out.append(t)

    for t in tasks:
        visit(t)
    return out


# =============================================================================== spec + questions
def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            v = v.strip()
            if not v.startswith(("'", '"')):
                v = re.sub(r"\s+#.*$", "", v)  # YAML comment: `status: approved   # set by the spec critic`
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def parse_acceptance_criteria(text: str, tag_regex: str) -> tuple[list[dict], list[str]]:
    """Criteria live under a heading containing 'acceptance'. Each must carry `[check: <ref>]`."""
    tag = re.compile(tag_regex, re.IGNORECASE)
    item = re.compile(r"^([-*]|\d+[.)])\s+")
    bodies: list[str] = []
    in_section = False
    current: Optional[list] = None  # lines of the list item being read; wrapped lines are joined to it
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            in_section = "acceptance" in line.lower()
            current = None
            continue
        if not in_section:
            continue
        if item.match(line):
            current = [item.sub("", line)]
            bodies.append(current)
        elif line and current is not None and raw[:1] in (" ", "\t"):
            current.append(line)  # an indented continuation of the previous criterion
        else:
            current = None
    criteria, untagged = [], []
    for parts in bodies:
        body = " ".join(parts)
        m = tag.search(body)
        if m:
            criteria.append({"text": tag.sub("", body).strip(), "ref": m.group("ref").strip()})
        else:
            untagged.append(body)
    return criteria, untagged


_Q_HEADING = re.compile(r"^##\s+Q\d+\b", re.MULTILINE)
_ANSWER = re.compile(r"^\s*[-*]?\s*\**Answer\**\s*:\s*(.*)$", re.IGNORECASE)


def parse_questions(text: str) -> tuple[int, int]:
    """Return (questions, answered). A question is a `## Q<n>` section; it is answered when its
    `Answer:` line has text after the colon (or on following lines before the next question)."""
    blocks = _Q_HEADING.split(text)[1:]
    answered = 0
    for b in blocks:
        lines = b.splitlines()
        for i, line in enumerate(lines):
            m = _ANSWER.match(line)
            if m:
                rest = m.group(1).strip() or " ".join(l.strip() for l in lines[i + 1:] if l.strip() and not l.strip().startswith("#"))
                if rest and rest.lower() not in ("todo", "tbd", "?", "(fill in)"):
                    answered += 1
                break
    return len(blocks), answered


def blocked_question(text: str) -> Optional[str]:
    """The question when an agent's answer ends with `BLOCKED: <question>` (the assumptions protocol), else None."""
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    if lines and lines[-1].upper().startswith("BLOCKED:"):
        return lines[-1].split(":", 1)[1].strip() or "(no question given)"
    return None


# =============================================================================== checks
def run_checks(cfg: dict, cwd: Path, only: Optional[list[str]] = None,
               task_tests: Optional[list[str]] = None) -> tuple[bool, str, list[dict]]:
    results, ok, errors = [], True, []
    tail = int(cfg.get("check_output_tail_lines", 200))
    for chk in cfg["checks"]:
        if only and chk["name"] not in only:
            continue
        cmd = str(chk["cmd"]).replace("{task_tests}", " ".join(task_tests or []))
        if cmd.lstrip().startswith("#"):
            continue
        t0 = time.monotonic()
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        passed = r.returncode == 0
        results.append({"name": chk["name"], "passed": passed, "seconds": round(time.monotonic() - t0, 1)})
        if not passed:
            ok = False
            out = trim_output(r.stdout + "\n" + r.stderr, tail, int(cfg.get("check_output_max_bytes", 16000)))
            errors.append(f"### check `{chk['name']}` failed (`{cmd}`)\n" + out)
            break
    return ok, "\n\n".join(errors), results


_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
MAX_LINE_CHARS = 2000


def trim_output(text: str, tail_lines: int, max_bytes: int) -> str:
    """The end of a check's output, small enough to go into the next prompt: colour codes stripped, very long lines
    (minified bundles, snapshot diffs) cut, at most `tail_lines` lines and `max_bytes` bytes — the end is kept,
    because that is where test runners print the failures and the summary."""
    lines = []
    for line in _ANSI.sub("", text).strip().splitlines()[-tail_lines:]:
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + f" … [{len(line) - MAX_LINE_CHARS} more characters cut]"
        lines.append(line)
    out, size = [], 0
    for line in reversed(lines):
        size += len(line.encode("utf-8")) + 1
        if size > max_bytes and out:
            out.append(f"… [{len(lines) - len(out)} earlier lines cut to keep the prompt small]")
            break
        out.append(line)
    return "\n".join(reversed(out))


_NUM = re.compile(r"\b\d+\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_PATH = re.compile(r"(/[\w.\-]+)+")


def error_signature(errors: str) -> str:
    names = re.findall(r"(?:FAILED|ERROR|FAIL)[:\s]+([\w./\-:\[\]]+)", errors)
    first = ""
    for line in errors.splitlines():
        if re.search(r"error|failed|exception|assert", line, re.IGNORECASE):
            first = line.strip()
            break
    norm = " ".join(sorted(set(names))) + " | " + first
    norm = _HEX.sub("0x", norm)
    norm = _PATH.sub("/P", norm)
    norm = _NUM.sub("N", norm)
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def is_contract_error(errors: str, cfg: dict) -> bool:
    return any(re.search(p, errors) for p in cfg["tests"].get("contract_error_patterns", []))


# =============================================================================== test lock
class TestLock:
    def __init__(self, repo: Path, patterns: list[str]):
        self.repo = repo
        self.patterns = patterns
        self.checksums: dict[str, str] = {}

    def matches(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p.replace("**/", "")) for p in self.patterns)

    def lock(self, files: Optional[list[str]] = None) -> None:
        files = files if files is not None else [
            str(p.relative_to(self.repo)) for p in self.repo.rglob("*")
            if p.is_file() and ".git" not in p.parts and self.matches(str(p.relative_to(self.repo)))
        ]
        self.checksums = {f: self._sha(f) for f in files if (self.repo / f).exists()}

    def _sha(self, f: str) -> str:
        return hashlib.sha256((self.repo / f).read_bytes()).hexdigest()

    def violations(self) -> list[str]:
        return [f for f, sha in self.checksums.items() if not (self.repo / f).exists() or self._sha(f) != sha]

    def to_json(self) -> dict:
        return dict(self.checksums)

    def from_json(self, d: dict) -> None:
        self.checksums = dict(d)


# =============================================================================== prompts
LEGACY_NAMES = {"plan-fidelity-critic": "spec-critic"}  # loop role/prompt names before 0.2.1


def _override(override_dir: Optional[Path], name: str) -> Optional[Path]:
    """A project override file, under the current name or the name it had before 0.2.1."""
    if not override_dir:
        return None
    for n in (name, LEGACY_NAMES.get(name)):
        if n and (override_dir / f"{n}.md").exists():
            return override_dir / f"{n}.md"
    return None


def load_prompt(name: str, override_dir: Optional[Path] = None) -> str:
    o = _override(override_dir, name)
    if o:
        return o.read_text(encoding="utf-8")
    return resources.files("semipilot").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")


def load_role(name: str, override_dir: Optional[Path] = None) -> str:
    o = _override(override_dir, name)
    if o:
        return o.read_text(encoding="utf-8")
    return resources.files("semipilot").joinpath("roles", f"{name}.md").read_text(encoding="utf-8")


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def _fill(template: str, kw: dict) -> str:
    return template.format_map(_Safe(**{k: (v if isinstance(v, str) else json.dumps(v, indent=2)) for k, v in kw.items()}))


def render_prompt(name: str, override_dir: Optional[Path] = None, role: Optional[str] = None,
                  role_dir: Optional[Path] = None, **kw) -> str:
    """The text of one loop call. With a role, the role definition comes first and the task follows under
    `# Your task` — the same prompt on every harness, no harness-specific agent files involved."""
    task = _fill(load_prompt(name, override_dir), kw)
    if not role:
        return task
    return f"{_fill(load_role(role, role_dir), kw).rstrip()}\n\n---\n\n{TASK_HEADING}\n\n{task}"


# =============================================================================== progress
@dataclass
class Progress:
    run_id: str
    feature: str
    branch: str
    started_at: str
    base_commit: str
    tasks: list = field(default_factory=list)
    budget: dict = field(default_factory=lambda: {"iterations_used": 0, "elapsed_min": 0.0})
    stop_reason: Optional[str] = None
    stop_detail: str = ""
    test_lock: dict = field(default_factory=dict)
    tests_commit: Optional[str] = None
    critique: list = field(default_factory=list)
    infra: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    check_results: list = field(default_factory=list)
    final_checks_passed: Optional[bool] = None

    @classmethod
    def load(cls, path: Path) -> "Progress":
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    def task(self, tid: str) -> dict:
        return next(t for t in self.tasks if t["id"] == tid)


# =============================================================================== orchestrator
class Loop:
    def __init__(self, repo: Path, cfg: dict, feature: str, sleep_fn=time.sleep, now_fn=None):
        self.repo = Path(repo).resolve()
        self.cfg = cfg
        self.feature = feature
        self.lay = Layout(self.repo)
        self.git = Git(self.repo)
        self.sleep = sleep_fn
        self.now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self.spec_path = self.lay.requirements(feature)
        self.questions_path = self.lay.open_questions(feature)
        self.decisions_path = self.lay.decisions(feature)
        self.rejections_path = self.lay.rejection_log(feature)
        self.progress_path = self.lay.progress(feature)
        self.report_path = self.lay.report(feature)
        self.spec_rel = self.lay.rel(self.spec_path)
        self.questions_rel = self.lay.rel(self.questions_path)
        self.decisions_rel = self.lay.rel(self.decisions_path)
        self.kl = knowledge_layer_present(self.repo, cfg)
        self.kb_validate_cmd, self.kb_resolve_cmd = kb_commands(self.repo, cfg)
        self._resolved: Optional[str] = None
        self.runner: Optional[Runner] = None
        self.progress: Optional[Progress] = None
        self.plan: Optional[dict] = None
        self.lock = TestLock(self.repo, cfg["tests"]["patterns"])
        self.t_start = time.monotonic()

    # ------------------------------------------------------------------ helpers
    def log(self, msg: str) -> None:
        print(f"[{self.now().astimezone().strftime('%H:%M:%S')}] {msg}", flush=True)

    def run_dir(self) -> Path:
        return self.lay.runs / self.progress.run_id

    def sdir(self) -> Path:
        return state_dir(self.cfg, self.repo, self.progress.run_id)

    def managed(self) -> list[str]:
        return self.lay.managed_paths(self.feature)

    def is_managed(self, path: str) -> bool:
        return any(path == m or path.startswith(m) for m in self.managed())

    def make_runner(self) -> Runner:
        carried = self.runner.cost_usd if self.runner else 0.0  # preflight calls count toward the run's cost
        carried_roles = dict(self.runner.cost_by_role) if self.runner else {}
        self.runner = Runner(self.cfg, self.run_dir(), sleep_fn=self.sleep, cwd=self.repo,
                             reset_tree_fn=lambda: self.reset_tree("infra failure"))
        self.runner.cost_usd = carried
        self.runner.cost_by_role = carried_roles
        return self.runner

    def instructions(self) -> tuple[str, str]:
        """(main instructions file, the list of instruction files to name in prompts)."""
        main = instructions_file(self.repo, self.cfg)
        present = [c for c in (main, *INSTRUCTION_CANDIDATES) if (self.repo / c).exists()]
        present = list(dict.fromkeys(present)) or [main]
        return main, ", ".join(f"`{c}`" for c in present)

    def prompt(self, name: str, **kw) -> str:
        main, listed = self.instructions()
        kw.setdefault("instructions_file", f"`{main}`")
        kw.setdefault("instructions", listed)
        return render_prompt(name, self.lay.custom_prompts, role=ROLE_FOR.get(name), role_dir=self.lay.custom_roles, **kw)

    def guard_branch(self, who: str) -> None:
        """Agents may not switch branches (the deny rules say so); verify it after every writing call."""
        if self.progress and self.progress.branch and self.git.current_branch() != self.progress.branch:
            now = self.git.current_branch()
            try:
                self.git.checkout(self.progress.branch)
                back = f"switched back to {self.progress.branch}"
            except RuntimeError as e:
                back = f"could not switch back to {self.progress.branch} ({e}); do it by hand before `semipilot resume`"
            raise HaltRun("guardrail_violation", f"{who} switched the branch to {now}; {back}")

    def last_good_commit(self) -> str:
        done = [t["commit"] for t in self.progress.tasks if t["status"] == "done" and t.get("commit")]
        return done[-1] if done else (self.progress.tests_commit or self.progress.base_commit)

    def reset_tree(self, why: str) -> None:
        if self.progress and self.progress.branch and self.git.branch_exists(self.progress.branch) \
                and self.git.current_branch() != self.progress.branch:
            # never hard-reset whatever branch an agent switched to (it may be main): switch back and halt instead
            self.guard_branch(f"an agent (before a tree reset for: {why})")
        sha = self.last_good_commit()
        discarded = self.git.reset_hard(sha, preserve=self.managed())
        if discarded:
            self.log(f"reset tree to {sha[:8]} ({why}); discarded: {', '.join(discarded)}")
            self.progress.warnings.append(f"tree reset ({why}) discarded {len(discarded)} file(s): {', '.join(discarded)}")

    def elapsed_min(self) -> float:
        return (time.monotonic() - self.t_start) / 60 + float(self.progress.budget.get("elapsed_min_before_resume", 0))

    def save(self) -> None:
        self.progress.budget["elapsed_min"] = round(self.elapsed_min(), 1)
        if self.runner:
            self.progress.infra = self.runner.outage.summary()
            self.progress.infra["harness"] = self.runner.harness.name
            if self.runner.cost_usd:
                before = float(self.progress.budget.get("cost_usd_before_resume", 0))
                self.progress.budget["cost_usd"] = round(before + self.runner.cost_usd, 4)
                by_role = dict(self.progress.budget.get("cost_by_role_before_resume") or {})
                for role, usd in self.runner.cost_by_role.items():
                    by_role[role] = round(by_role.get(role, 0) + usd, 4)
                self.progress.budget["cost_by_role"] = by_role
        self.progress.test_lock = self.lock.to_json()
        self.progress.save(self.progress_path)
        self.lay.last_run.write_text(self.feature + "\n", encoding="utf-8")

    def spec_text(self) -> str:
        return self.spec_path.read_text(encoding="utf-8") if self.spec_path.exists() else ""

    def criteria(self) -> list[dict]:
        c, _ = parse_acceptance_criteria(self.spec_text(), self.cfg["preflight"]["criterion_tag_regex"])
        return c

    def decisions_text(self) -> str:
        return self.decisions_path.read_text(encoding="utf-8") if self.decisions_path.exists() else "(none yet)"

    def questions_text(self) -> str:
        return self.questions_path.read_text(encoding="utf-8") if self.questions_path.exists() else "(no questions were asked)"

    def branch_name(self) -> str:
        """The run branch, from `git.branch` in the config: {type}/{feature} by default (conventional-branch
        style; {type} comes from the spec's frontmatter, feat when absent)."""
        g = self.cfg["git"]
        template = g.get("branch") or f"{g.get('branch_prefix', 'semipilot/')}{{feature}}-{{date}}"  # pre-0.2 configs
        fm = parse_frontmatter(self.spec_text())
        kind = re.sub(r"[^a-z0-9-]", "", str(fm.get("type") or "feat").lower()) or "feat"
        return template.format(type=kind, feature=self.feature, date=self.now().strftime("%Y%m%d"))

    def commit_message(self, subject: str, kind: Optional[str] = None) -> str:
        """A commit message from `git.commit`: {type}({feature}): {subject}. `kind` overrides the type for the
        loop's own commits (test, docs, chore); tasks use the spec's type (feat by default)."""
        g = self.cfg["git"]
        template = g.get("commit") or f"{g.get('commit_prefix', '[semipilot]')} {{subject}}"  # pre-0.2 configs
        if kind is None:
            fm = parse_frontmatter(self.spec_text())
            kind = re.sub(r"[^a-z0-9-]", "", str(fm.get("type") or "feat").lower()) or "feat"
        subject = subject[:1].lower() + subject[1:] if subject else subject
        return template.format(type=kind, feature=self.feature, subject=subject)

    def run_branches(self) -> dict[str, str]:
        """Branches created by earlier runs in this project: branch → feature (from each feature's progress file)."""
        out = {}
        for slug in self.lay.list_features():
            pp = self.lay.progress(slug)
            if pp.exists():
                try:
                    b = json.loads(pp.read_text(encoding="utf-8")).get("branch")
                except (OSError, ValueError):
                    continue
                if b:
                    out[b] = slug
        return out

    def find_checkpoint(self) -> Optional[tuple[str, dict]]:
        """(branch, progress) of this feature's latest run, wherever its checkpoint is: in the working tree, or
        committed on the run branch (where `finish` commits it — so it is not visible from the base branch)."""
        if self.progress_path.exists():
            try:
                data = json.loads(self.progress_path.read_text(encoding="utf-8"))
                if data.get("branch") and not str(data.get("run_id", "")).startswith("preflight-"):
                    return data["branch"], data
            except (OSError, ValueError):
                pass
        rel = self.lay.rel(self.progress_path)
        found = []
        for b in self.git.local_branches():
            text = self.git.show_file(b, rel)
            if not text:
                continue
            try:
                data = json.loads(text)
            except ValueError:
                continue
            if data.get("feature") == self.feature and data.get("branch") == b:
                found.append((data.get("started_at", ""), b, data))
        if not found:
            return None
        _, b, data = max(found, key=lambda x: x[0])
        return b, data

    def interrupted_run_message(self, branch: str, data: dict) -> str:
        stopped = data.get("stop_reason") or "interrupted before it could record a stop reason"
        base = self.git.current_branch()
        if stopped == "completed":
            return (f"'{self.feature}' was already built on branch {branch} (completed).\n"
                    f"  Review it:     semipilot review {self.feature}\n"
                    f"  Build again:   git branch -D {branch}, then semipilot run {self.feature}")
        return (f"'{self.feature}' already has a run on branch {branch} (stopped: {stopped}).\n"
                f"  Continue it:  semipilot resume {self.feature}\n"
                f"  Start over:   git branch -D {branch}   (from {base if base != branch else 'your base branch'}), "
                f"then semipilot run {self.feature}")

    def ensure_gitignore(self) -> None:
        gi = self.lay.root / ".gitignore"
        self.lay.root.mkdir(parents=True, exist_ok=True)
        if not gi.exists() or "runs/" not in gi.read_text(encoding="utf-8"):
            with open(gi, "a", encoding="utf-8") as f:
                f.write("runs/\nlast-run\n")

    # ------------------------------------------------------------------ preflight
    def check_spec(self) -> list[dict]:
        if not self.spec_path.exists():
            raise PreflightError(f"{self.spec_rel} not found. In your agent's chat run `/semipilot-refine <your idea>`, "
                                 "then `/semipilot-spec-critic`.")
        text = self.spec_text()
        fm = parse_frontmatter(text)
        if str(fm.get("status", "")).lower() != "approved":
            here = self.git.current_branch()
            elsewhere = [b for b in self.git.local_branches(30) if b != here
                         and str(parse_frontmatter(self.git.show_file(b, self.spec_rel) or "").get("status", "")).lower() == "approved"]
            hint = (f" It IS approved on branch {elsewhere[0]}: check out the branch the feature should be built on and "
                    f"bring the approved {self.spec_rel} there (e.g. `git checkout {elsewhere[0]} -- {self.spec_rel}`)."
                    if elsewhere else
                    " Run `/semipilot-spec-critic` in your agent's chat and reply `approve` (or set `status: approved` "
                    "in its frontmatter yourself).")
            raise PreflightError(f"{self.spec_rel} is not approved on branch {here} "
                                 f"(status: {fm.get('status') or 'missing'}).{hint}")
        crit, untagged = parse_acceptance_criteria(text, self.cfg["preflight"]["criterion_tag_regex"])
        if untagged:
            raise PreflightError("acceptance criteria without a machine-checkable [check: ...] tag:\n  - "
                                 + "\n  - ".join(untagged) + "\nEvery criterion must name a test, lint, typecheck or build check.")
        if not crit:
            raise PreflightError("no acceptance criteria found under an '## Acceptance criteria' heading")
        return crit

    def check_knowledge_layer(self) -> None:
        if not self.kl:
            return
        cmd = self.kb_validate_cmd
        r = subprocess.run(cmd, shell=True, cwd=self.repo, capture_output=True, text=True)
        if r.returncode != 0:
            raise PreflightError(f"knowledge layer unhealthy (`{cmd}` failed) — fix the cards before a run:\n{(r.stdout + r.stderr)[-1500:]}")
        self.log("knowledge layer healthy")
        if self.tags():
            self.resolved_knowledge()  # unknown tags fail here, before anything is spent
            self.log(f"knowledge resolved for tags {', '.join(self.tags())}")

    def resolved_knowledge(self) -> str:
        """The reading list for the requirements' tags, resolved once per run by the orchestrator (deterministic, and
        no agent needs shell access to retrieve knowledge)."""
        if self._resolved is None:
            cmd = self.kb_resolve_cmd.replace("{tags}", shlex.quote(",".join(self.tags())))
            r = subprocess.run(cmd, shell=True, cwd=self.repo, capture_output=True, text=True)
            if r.returncode != 0:
                raise PreflightError(f"knowledge layer: `{cmd}` failed — fix the tags under Knowledge References in "
                                     f"{self.spec_rel} or the cards:\n{(r.stdout + r.stderr)[-1500:]}")
            self._resolved = r.stdout.strip()
        return self._resolved

    def tags(self) -> list[str]:
        """Tags from `requirements.md > Knowledge References > Tags:` — the retrieval key for the knowledge layer."""
        m = re.search(r"^\s*[-*]?\s*\**Tags\**\s*:\s*(.+)$", self.spec_text(), re.MULTILINE | re.IGNORECASE)
        if not m:
            return []
        tags = [t.strip().strip("`*_") for t in re.split(r"[,\s]+", m.group(1))]
        tags = [t for t in tags if t]
        bad = [t for t in tags if not re.fullmatch(r"[a-z0-9-]+", t)]
        if bad:  # tags reach a shell command line: only the vocabulary's own alphabet is accepted
            raise PreflightError(f"invalid knowledge tag(s) {', '.join(repr(b) for b in bad)} under Knowledge References in "
                                 f"{self.spec_rel}: tags are lowercase letters, digits and hyphens")
        return tags

    def kl_context(self) -> dict:
        """Prompt variables describing where module knowledge comes from. With a knowledge layer the orchestrator
        has already resolved the requirements' tags; the agent gets the exact reading list, not a command to run."""
        _, listed = self.instructions()
        protected = (f"Never modify `docs/cards/`, {listed}, `AGENTS.md`, `CLAUDE.md` or `.github/instructions/` — the "
                     "semipilot-scribe skill does that after the human review.")
        if self.kl:
            tags = self.tags()
            if tags:
                where = ("This repository has a knowledge layer. Module knowledge comes from it, not from searching the "
                         f"codebase. The orchestrator resolved the requirements' tags ({', '.join(tags)}); read ONLY the "
                         "cards (L1) below and the deep docs (L2) a card points you to, and open code only inside the "
                         "listed code paths (L3):\n\n```\n" + self.resolved_knowledge() + "\n```\n\n")
            else:
                where = ("This repository has a knowledge layer, but the requirements list no tags under Knowledge "
                         "References: read `docs/cards/_vocabulary.md`, pick the 1–4 matching tags, read the cards "
                         "that own them (`docs/cards/*.md`, `owns:`) and say which tags you used. ")
            return {"knowledge": where + "Honor every card's `invariants:` and `public_contracts:`. " + protected,
                    "knowledge_updates_rule": (
                        "Also output `knowledge_updates`: one line per card owning a changed file (`docs/cards/<card>.md: "
                        "<delta or 'no change'>`), plus `.github/instructions/<area>.instructions.md`, `docs/decisions.md` "
                        "(ADR title or 'no change'), `docs/dependencies.md`, and the `docs/CHANGELOG.md` line. "
                        "The semipilot-scribe skill executes this list after the human review; the loop never touches "
                        "those files.")}
        return {"knowledge": (
            f"Follow the repository's instructions: {listed}, and any `.github/instructions/*.instructions.md` whose "
            "`applyTo` matches the files involved. " + protected),
            "knowledge_updates_rule": "`knowledge_updates` may be omitted (no knowledge layer in this repository)."}

    def render_implementation_plan(self) -> None:
        """implementation-plan.md: the plan in the manual pipeline's vocabulary, for the human and for semipilot-scribe."""
        if not self.plan:
            return
        L = [f"# Implementation Plan — {self.feature}", "",
             f"Generated by PilotInLoop run `{self.progress.run_id}` from `{self.spec_rel}`. Source of truth for the run: `plan.json`.", "",
             "## Tasks", ""]
        for t in topo_sort(self.plan["tasks"]):
            L += [f"### {t['id']} — {t['title']} ({t['size']})", "", t["description"], "",
                  f"- Depends on: {', '.join(t['depends_on']) or 'none'}",
                  f"- Files to change: {', '.join('`' + f + '`' for f in t['expected_files'])}",
                  f"- Test plan (acceptance refs): {', '.join(t['acceptance_checks'])}"]
            if t.get("interfaces"):
                L += ["- Interfaces:"] + [f"  - `{i}`" for i in t["interfaces"]]
            L += [""]
        L += ["## Knowledge Updates Required", "",
              "What the semipilot-scribe skill must update after the human review (the loop never touches these files):", ""]
        L += [f"- {k}" for k in self.plan.get("knowledge_updates") or []] or ["- (planner listed none" + (" — check the cards owning the changed files)" if self.kl else ")")]
        L += [""]
        self.lay.implementation_plan(self.feature).write_text("\n".join(L), encoding="utf-8")

    def check_config(self) -> None:
        try:
            get_harness(self.cfg)
        except UnknownHarnessError as e:
            raise PreflightError(f"{e} (set `harness:` in .semipilot/config.yaml)")
        if not self.cfg.get("checks"):
            raise PreflightError("no `checks` configured in .semipilot/config.yaml (run `semipilot init`, then edit)")
        for chk in self.cfg["checks"]:
            if str(chk.get("cmd", "")).lstrip().startswith("#"):
                raise PreflightError(f"check `{chk.get('name')}` is still a TODO in .semipilot/config.yaml")

    def commit_feature_files(self, what: str) -> None:
        """If the only uncommitted files are this feature's own Markdown (spec, answers), commit them —
        that is the human's gate work, and asking them to git-add it is a papercut."""
        feat_rel = self.lay.rel(self.lay.feature_dir(self.feature)) + "/"
        dirty = self.git.status_paths()
        if dirty and all(f.startswith(feat_rel) or f.startswith(self.lay.rel(self.lay.root) + "/.gitignore") for f in dirty):
            self.git.run("add", "-A", "--", feat_rel, self.lay.rel(self.lay.root / ".gitignore"))
            self.git.run("commit", "-q", "--no-verify", "-m", self.commit_message(what, kind="docs"))
            self.log(f"committed {feat_rel} ({what})")

    def check_no_earlier_run(self) -> None:
        """A second `run` of a feature whose run branch exists is almost always a retry after an interruption:
        say `resume`, before any other check can send the user somewhere else."""
        cp = self.find_checkpoint()
        if cp and self.git.branch_exists(cp[0]):
            raise PreflightError(self.interrupted_run_message(*cp))

    def check_tree(self, stack: bool = False) -> None:
        self.commit_feature_files("spec and answers")
        if self.git.is_dirty():
            raise PreflightError("working tree is dirty; commit or stash before a run")
        if self.git.branch_exists(self.branch_name()):
            raise PreflightError(f"branch {self.branch_name()} already exists; delete it, or pass --branch <name> "
                                 f"(the pattern is `git.branch` in .semipilot/config.yaml)")
        base = self.git.current_branch()
        earlier = self.run_branches()
        if base in earlier and not stack:
            raise PreflightError(f"you are on {base}, the branch of an earlier semipilot run ({earlier[base]}). The run "
                                 f"branches off the branch you are on, so this would stack the feature on top of that "
                                 f"unreviewed work. Check out your base branch first (e.g. `git checkout main`), or pass "
                                 f"--stack if stacking is what you want.")
        if base == "HEAD":
            raise PreflightError("detached HEAD; check out the branch the feature should be built on")
        self.log(f"base: {base} @ {self.git.head()[:10]} → the run will create {self.branch_name()} from here")

    def check_agent(self) -> None:
        """Free checks only: the agent CLI is installed (and the optional auth/expiry checks). No model call — the
        planner's questions call right after is the first real call, and a login problem there halts cleanly before
        any branch exists (with --no-questions, `resume` after logging in continues at planning)."""
        h = self.runner.harness
        if shutil.which(h.executable[0]) is None:
            raise PreflightError(f"{h.label} not found ({h.executable[0]}): {h.install_hint}")
        pf = self.cfg["preflight"]
        if pf.get("auth_check_cmd"):
            r = subprocess.run(pf["auth_check_cmd"], shell=True, cwd=self.repo, capture_output=True, text=True)
            if r.returncode != 0:
                raise PreflightError(f"auth check `{pf['auth_check_cmd']}` failed:\n{(r.stdout + r.stderr)[-1500:]}")
        exp_env = next((e for e in (pf.get("token_expiry_env"), "COPILOT_TOKEN_EXPIRES_AT") if e and os.environ.get(e)), None)
        if exp_env:
            expires = dt.datetime.fromisoformat(os.environ[exp_env])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=dt.timezone.utc)
            need = dt.timedelta(seconds=self.cfg["budget"]["wall_clock_seconds"])
            if expires < self.now() + need:
                raise PreflightError(f"token expires at {expires.isoformat()} — before the {need} wall-clock budget ends")

    def ask_questions(self, crit: list[dict]) -> int:
        """Questions-only planner pass. Writes questions.md; returns the number of questions."""
        prompt = self.prompt("planner-questions", feature=self.feature, spec_path=self.spec_rel, criteria=crit, **self.kl_context())
        res = self.runner.run("planner", prompt, "planner-questions")
        text = res.text.strip() + "\n"
        self.questions_path.parent.mkdir(parents=True, exist_ok=True)
        self.questions_path.write_text(text, encoding="utf-8")
        n, _ = parse_questions(text)
        return n

    # ------------------------------------------------------------------ run
    def run(self, skip_questions: bool = False, preflight_only: bool = False, stack: bool = False) -> str:
        """Full run. Raises NeedsAnswers when the human has questions to answer first.
        `preflight_only` stops after the checks and the questions (step 3 of the flow).
        The run branch is created from the branch that is checked out; `stack` allows that to be another
        semipilot branch."""
        self.ensure_gitignore()
        self.check_config()
        self.check_no_earlier_run()
        crit = self.check_spec()
        self.check_knowledge_layer()
        self.check_tree(stack=stack)
        self.log(f"{self.feature}: {len(crit)} tagged acceptance criteria, requirements approved, tree clean")

        # temporary progress for the preflight logs
        pre_id = f"preflight-{self.feature}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        self.progress = Progress(run_id=pre_id, feature=self.feature, branch=self.branch_name(),
                                 started_at=self.now().isoformat(), base_commit=self.git.head())
        self.make_runner()
        self.check_agent()
        self.log(f"{self.runner.harness.label} installed ({self.runner.harness.executable[0]})")

        if not skip_questions:
            if self.questions_path.exists():
                n, answered = parse_questions(self.questions_path.read_text(encoding="utf-8"))
                if n and answered < n:
                    raise NeedsAnswers(self.questions_path, n - answered)
                self.log(f"questions: {answered}/{n} answered")
            else:
                n = self.ask_questions(crit)
                if n:
                    # keep the questions file so the human can answer; the tree is otherwise untouched
                    raise NeedsAnswers(self.questions_path, n)
                self.log("planner has no open questions")
        self.commit_feature_files("questions")
        if preflight_only:
            self.log("preflight OK — ready to run")
            return "preflight_ok"
        if self.git.is_dirty():
            raise PreflightError("working tree is dirty; commit or stash before a run")

        # the real run
        base_branch = self.git.current_branch()
        branch = self.branch_name()
        self.git.create_branch(branch)
        run_id = f"{self.feature}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        self.progress = Progress(run_id=run_id, feature=self.feature, branch=branch,
                                 started_at=self.now().isoformat(), base_commit=self.git.head())
        self.decisions_path.write_text(f"# Decisions — {self.feature} ({run_id})\n\n"
                                       "Assumptions the loop made where the spec was silent. Read before the diff.\n\n",
                                       encoding="utf-8")
        self.make_runner()
        self.save()
        self.log(f"run {run_id} on branch {branch} (from {base_branch})")
        try:
            self.stage_plan(crit)
            self.stage_tests(crit)
            self.stage_implement()
            self.progress.stop_reason = self.progress.stop_reason or self.end_reason()
        except HaltRun as h:
            self.on_halt(h)
        finally:
            self.finish()
        return self.progress.stop_reason

    def end_reason(self) -> str:
        """`completed` only when every task is done; tasks left blocked make it `completed_with_blocked`."""
        return "completed" if all(t["status"] == "done" for t in self.progress.tasks) else "completed_with_blocked"

    def on_halt(self, h: HaltRun) -> None:
        self.progress.stop_reason, self.progress.stop_detail = h.reason, h.detail
        for t in self.progress.tasks:
            if t["status"] == "in_progress":
                t["status"] = "pending"
                if t["attempts"] > 0:
                    t["attempts"] -= 1
                    self.progress.budget["iterations_used"] = max(0, self.progress.budget["iterations_used"] - 1)
        self.log(f"HALT: {h.reason} — {h.detail}")

    def resume(self) -> str:
        cp = self.find_checkpoint()
        if not cp or not self.git.branch_exists(cp[0]):
            raise PreflightError(f"nothing to resume for '{self.feature}': no run has started yet (no checkpoint on "
                                 f"any local branch). Start one with `semipilot run {self.feature}`.")
        branch = cp[0]
        if self.git.current_branch() != branch:
            if self.git.is_dirty():
                raise PreflightError(f"the run is on branch {branch}, but you are on {self.git.current_branch()} with "
                                     "uncommitted changes; commit or stash them, then `semipilot resume "
                                     f"{self.feature}` again (it switches to {branch} itself)")
            self.git.checkout(branch)
            self.log(f"switched to the run branch {branch}")
        self.progress = Progress.load(self.progress_path)
        self.progress.budget["elapsed_min_before_resume"] = self.progress.budget.get("elapsed_min", 0)
        self.progress.budget["cost_usd_before_resume"] = self.progress.budget.get("cost_usd", 0)
        self.progress.budget["cost_by_role_before_resume"] = dict(self.progress.budget.get("cost_by_role") or {})
        self.t_start = time.monotonic()  # an automatic resume after a retry window must not count the sleep
        self.progress.stop_reason = None
        self.lock.from_json(self.progress.test_lock)
        plan_path = self.sdir() / "plan.json"
        if not plan_path.exists() and self.lay.plan_json(self.feature).exists():
            plan_path.write_text(self.lay.plan_json(self.feature).read_text(encoding="utf-8"), encoding="utf-8")
        self.plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
        if self.plan is None and self.progress.tasks:
            raise PreflightError(f"plan.json missing at {plan_path} and in {self.lay.rel(self.lay.feature_dir(self.feature))}")
        self.make_runner()
        if self.git.is_dirty():
            self.reset_tree("resume with dirty tree")
        for t in self.progress.tasks:
            if t["status"] == "in_progress":
                t["status"] = "pending"
            elif t["status"] == "blocked":
                # resume after answering the question / fixing the cause: the task gets a fresh set of attempts
                t.update({"status": "pending", "attempts": 0, "blocked_reason": None, "contract_fixes": 0,
                          "scope_violations": 0})
        try:
            crit = self.criteria()
            if self.plan is None:  # halted while planning (outage, quota, BLOCKED:): plan again
                self.stage_plan(crit)
            if self.progress.tests_commit is None:  # halted before the tests were locked: write them now
                self.stage_tests(crit)
            self.stage_implement()
            self.progress.stop_reason = self.progress.stop_reason or self.end_reason()
        except HaltRun as h:
            self.on_halt(h)
        finally:
            self.finish()
        return self.progress.stop_reason

    def finish(self) -> None:
        try:
            if self.plan:
                self.lay.plan_json(self.feature).write_text(json.dumps(self.plan, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        self.save()
        self.write_report()
        self.commit_state()
        self.maybe_schedule_retry()

    def commit_state(self) -> None:
        if self.progress.branch and self.git.branch_exists(self.progress.branch) and self.git.current_branch() != self.progress.branch:
            self.log(f"not committing run state: {self.git.current_branch()} is checked out, not {self.progress.branch}")
            return
        self.ensure_gitignore()
        paths = [m for m in self.managed() if (self.repo / m.rstrip("/")).exists() and not m.endswith("runs/")]
        paths.append(self.lay.rel(self.lay.root / ".gitignore"))
        self.git.run("add", "-A", "--", *paths)
        if self.git.run("diff", "--cached", "--name-only").strip():
            self.git.run("commit", "-q", "--no-verify", "-m", self.commit_message(f"run state ({self.progress.stop_reason or 'update'})", kind="chore"))

    def maybe_schedule_retry(self) -> None:
        win = self.cfg["infra"].get("retry_window")
        if not win or self.progress.stop_reason not in (AGENT_UNAVAILABLE, LEGACY_AGENT_UNAVAILABLE):
            return
        hh, mm = (int(x) for x in win.split(":"))
        now = self.now().astimezone()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now < target:
            wait = (target - now).total_seconds()
            self.log(f"breaker tripped before {win}; sleeping {wait / 60:.0f} min then resuming once")
            self.sleep(wait)
            self.resume()

    # ------------------------------------------------------------------ plan + critique
    def stage_plan(self, crit: list[dict]) -> None:
        rejections_text, plan, accepted = "", None, False
        rounds = self.cfg["budget"]["max_critique_rounds"]
        for rnd in range(rounds):
            plan = self.call_planner(crit, rejections_text)
            verdicts = self.call_critics(plan, rnd)
            if all(v["verdict"] == "accept" for v in verdicts):
                self.log(f"plan accepted by critics (round {rnd + 1}, {len(plan['tasks'])} tasks)")
                accepted = True
                break
            rejections_text = "\n\n".join(f"### {v['critic']}\n" + "\n".join(f"- {i}" for i in v["issues"]) for v in verdicts if v["verdict"] != "accept")
            self.append_rejection_log(rnd, verdicts)
        if not accepted:
            raise HaltRun("plan_rejected", f"critics rejected the plan {rounds} time(s); see {self.lay.rel(self.rejections_path)}")
        self.plan = plan
        (self.sdir() / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self.render_implementation_plan()
        self.progress.tasks = [
            {"id": t["id"], "title": t["title"], "status": "pending", "attempts": 0, "commit": None,
             "blocked_reason": None, "contract_fixes": 0, "diff": None}
            for t in topo_sort(plan["tasks"])
        ]
        self.save()

    def call_planner(self, crit: list[dict], rejections: str) -> dict:
        for attempt in range(1, 3):
            prompt = self.prompt("planner-plan", feature=self.feature, spec_path=self.spec_rel,
                                 questions_path=self.questions_rel, criteria=crit, rejections=rejections or "(none)",
                                 max_files=self.cfg["guardrails"]["max_expected_files_per_task"], **self.kl_context())
            res = self.runner.run("planner", prompt, f"planner-plan-{attempt}")
            q = blocked_question(res.text)
            if q:
                raise HaltRun("blocked", f"the planner needs an answer: {q}")
            plan = Runner.extract_json(res.text)
            errors = validate_plan(plan, self.cfg, crit) if plan else ["no JSON object found in planner output"]
            if not errors:
                return plan
            self.log(f"plan attempt {attempt} invalid: {errors}")
            rejections = (rejections + "\n\n### Schema/sizing validation errors\n" + "\n".join(f"- {e}" for e in errors)).strip()
        raise HaltRun("plan_rejected", "planner could not produce a valid plan in 2 attempts")

    def call_critics(self, plan: dict, rnd: int) -> list[dict]:
        out = []
        for critic in ("plan-fidelity-critic", "plan-critic"):
            prompt = self.prompt(critic, plan_json=plan, spec_path=self.spec_rel, questions_path=self.questions_rel,
                                 max_files=self.cfg["guardrails"]["max_expected_files_per_task"], **self.kl_context())
            res = self.runner.run(critic, prompt, f"{critic}-round{rnd + 1}")
            v = Runner.extract_json(res.text) or {"verdict": "reject", "issues": ["critic returned no JSON verdict"]}
            v.setdefault("issues", [])
            v["critic"] = critic
            out.append(v)
        self.progress.critique.append({"round": rnd + 1, "verdicts": out})
        return out

    def append_rejection_log(self, rnd: int, verdicts: list[dict]) -> None:
        self.rejections_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rejections_path, "a", encoding="utf-8") as f:
            f.write(f"\n## {self.now().date()} — run {self.progress.run_id} — critique round {rnd + 1}\n")
            for v in verdicts:
                if v["verdict"] != "accept":
                    f.write(f"### {v['critic']}\n")
                    for i in v["issues"]:
                        f.write(f"- {i}\n")

    # ------------------------------------------------------------------ tests first
    def stage_tests(self, crit: list[dict]) -> None:
        prompt = self.prompt("test-writer", spec_path=self.spec_rel, questions_path=self.questions_rel,
                             decisions_path=self.decisions_rel, criteria=crit,
                             plan_tasks=[{k: t[k] for k in ("id", "title", "expected_files", "acceptance_checks", "interfaces") if k in t}
                                         for t in self.plan["tasks"]],
                             test_patterns=self.cfg["tests"]["patterns"], **self.kl_context())
        res = self.runner.run("test-writer", prompt, "test-writer")
        self.guard_branch("the test-writer")
        q = blocked_question(res.text)
        if q:
            self.reset_tree("test-writer blocked")
            raise HaltRun("blocked", f"the test-writer needs an answer: {q}")
        changed = [f for f in self.git.changed_files(self.progress.base_commit) if not self.is_managed(f)]
        non_test = [f for f in changed if not self.lock.matches(f)]
        if non_test:
            self.git.restore_paths(self.progress.base_commit, non_test)
            self.progress.warnings.append(f"test-writer touched non-test files, reverted: {', '.join(non_test)}")
        self.lock.lock()
        sha = self.git.commit(self.commit_message("acceptance tests (locked)", kind="test"), exclude=self.managed())
        self.progress.tests_commit = sha
        self.log(f"locked {len(self.lock.checksums)} test file(s) at {sha[:8]}")
        self.save()

    # ------------------------------------------------------------------ implement loop
    def budget_exhausted(self) -> Optional[str]:
        b = self.cfg["budget"]
        if self.progress.budget["iterations_used"] >= b["max_iterations"]:
            return "budget_exhausted: max_iterations"
        if self.elapsed_min() * 60 >= b["wall_clock_seconds"]:
            return "budget_exhausted: wall_clock"
        return None

    def stage_implement(self) -> None:
        by_id = {t["id"]: t for t in self.plan["tasks"]}
        for entry in self.progress.tasks:
            if entry["status"] == "done":
                continue
            task = by_id[entry["id"]]
            blocked_dep = next((d for d in task["depends_on"] if self.progress.task(d)["status"] != "done"), None)
            if blocked_dep:
                self.mark(entry, "blocked", f"dependency {blocked_dep} is not done")
                continue
            why = self.budget_exhausted()
            if why:
                self.progress.stop_reason = "budget_exhausted"
                self.progress.stop_detail = why
                self.log(f"stopping: {why}")
                break
            self.run_task(task, entry)
            self.save()
            if self.run_diff_exceeded():
                self.progress.stop_reason = "budget_exhausted"
                self.progress.stop_detail = "diff_cap_lines_per_run exceeded"
                break
        self.final_checks()

    def run_task(self, task: dict, entry: dict) -> None:
        g = self.cfg["guardrails"]
        max_retries = self.cfg["budget"]["max_retries_per_task"]
        entry["status"] = "in_progress"
        base = self.last_good_commit()
        last_errors, seen = None, set()
        while entry["attempts"] < max_retries:
            if self.budget_exhausted():
                entry["status"] = "pending"
                return
            entry["attempts"] += 1
            self.progress.budget["iterations_used"] += 1
            label = f"{task['id']}-attempt{entry['attempts']}"
            self.log(f"{task['id']} {task['title']!r} attempt {entry['attempts']}/{max_retries}")
            prompt = self.prompt("implementer", task_json=task, task_id=task["id"], expected_files=task["expected_files"],
                                 spec_path=self.spec_rel, questions_path=self.questions_rel, decisions_path=self.decisions_rel,
                                 locked_tests=sorted(self.lock.checksums), errors=last_errors or "(first attempt — no previous errors)",
                                 **self.kl_context())
            res = self.runner.run("implementer", prompt, label)
            self.save()
            self.guard_branch(f"the implementer ({task['id']})")
            q = blocked_question(res.text)
            if q:
                self.reset_tree(f"{task['id']} blocked by a question")
                self.mark(entry, "blocked", f"BLOCKED: {q}")
                return
            if res.timed_out:
                self.reset_tree(f"{task['id']} call timeout")
                last_errors = "previous attempt timed out"
                continue
            viol = self.lock.violations()
            if viol:
                self.git.restore_paths(self.progress.tests_commit or base, viol)
                self.progress.warnings.append(f"{task['id']}: implementer modified locked tests, reverted: {', '.join(viol)}")
                last_errors = f"You modified locked test files ({', '.join(viol)}). Those changes were reverted. Make the implementation satisfy the tests instead."
                continue
            ok_scope, scope_msg, _ = self.enforce_scope(task, base)
            if not ok_scope:
                self.reset_tree(f"{task['id']} scope violation")
                self.progress.warnings.append(f"{task['id']}: scope violation: {scope_msg}")
                last_errors = f"Scope violation: {scope_msg}. Your attempt was reverted. Only touch: {', '.join(task['expected_files'])}."
                if entry.get("scope_violations", 0) >= 1:
                    self.mark(entry, "blocked", f"repeated scope violation: {scope_msg}")
                    return
                entry["scope_violations"] = entry.get("scope_violations", 0) + 1
                continue
            if scope_msg:
                self.progress.warnings.append(f"{task['id']}: {scope_msg}")
            add, rem = self.git.diff_lines(base, exclude=self.managed())
            if add + rem > g["diff_cap_lines_per_task"]:
                self.reset_tree(f"{task['id']} diff cap")
                self.mark(entry, "blocked", f"diff of {add + rem} lines exceeds per-task cap {g['diff_cap_lines_per_task']}")
                return
            ok, errors, results = run_checks(self.cfg, self.repo, task_tests=self.task_tests(task))
            self.progress.check_results = results
            if ok:
                sha = self.git.commit(self.commit_message(f"{task['title']} ({task['id']})"), exclude=self.managed())
                entry["commit"] = sha
                entry["diff"] = self.git.stat_between(base, sha)
                self.mark(entry, "done")
                self.log(f"{task['id']} done → {sha[:8]}")
                return
            if viol == [] and is_contract_error(errors, self.cfg) and entry["contract_fixes"] < self.cfg["budget"]["max_contract_fixes_per_task"]:
                entry["contract_fixes"] += 1
                if self.fix_test_contract(task, errors):
                    ok, errors, results = run_checks(self.cfg, self.repo, task_tests=self.task_tests(task))
                    if ok:
                        sha = self.git.commit(self.commit_message(f"{task['title']} ({task['id']})"), exclude=self.managed())
                        entry["commit"], entry["diff"] = sha, self.git.stat_between(base, sha)
                        self.mark(entry, "done")
                        return
            last_errors = errors
            if g["stuck_detection"]:
                sig = error_signature(errors)
                if sig in seen:
                    self.log(f"{task['id']}: same error twice → stuck")
                    break
                seen.add(sig)
        if entry["status"] != "done":
            self.reset_tree(f"{task['id']} gave up")
            self.mark(entry, "blocked", self.summarize(last_errors))

    def fix_test_contract(self, task: dict, errors: str) -> bool:
        self.log(f"{task['id']}: contract error in locked tests → test-fixer")
        before = dict(self.lock.checksums)
        prompt = self.prompt("test-fixer", task_json=task, errors=errors, locked_tests=sorted(before), decisions_path=self.decisions_rel)
        self.runner.run("test-fixer", prompt, f"{task['id']}-testfix")
        self.guard_branch(f"the test-fixer ({task['id']})")
        impl_files = set(task["expected_files"])
        changed = [f for f in self.git.changed_files(self.last_good_commit()) if not self.is_managed(f)]
        bad = [f for f in changed if f not in before and f not in impl_files and not self.lock.matches(f)]
        if bad:
            self.git.restore_paths(self.last_good_commit(), bad)
        touched = [f for f in before if (self.repo / f).exists() and hashlib.sha256((self.repo / f).read_bytes()).hexdigest() != before[f]]
        if not touched:
            return False
        add, rem = self.git.diff_lines(self.last_good_commit(), touched)
        self.progress.warnings.append(f"{task['id']}: test-fixer edited {', '.join(touched)} (+{add}/-{rem}) — REVIEW: contract fix, not an assertion change")
        self.lock.lock(list(before))
        return True

    def enforce_scope(self, task: dict, base: str) -> tuple[bool, str, list[str]]:
        g = self.cfg["guardrails"]
        changed = [f for f in self.git.changed_files(base) if not self.is_managed(f)]
        expected = set(task["expected_files"])
        others = {f for t in self.plan["tasks"] if t["id"] != task["id"] for f in t["expected_files"]} - expected
        extra = [f for f in changed if f not in expected]
        new_tests = [f for f in extra if self.lock.matches(f) and f not in self.lock.checksums]
        if g.get("allow_new_test_files", True):
            extra = [f for f in extra if f not in new_tests]
        clash = [f for f in extra if f in others]
        if clash:
            return False, f"touched files owned by another task: {', '.join(clash)}", extra
        if len(extra) > g["scope_tolerance_extra_files"]:
            return False, f"{len(extra)} files outside expected_files (tolerance {g['scope_tolerance_extra_files']}): {', '.join(extra)}", extra
        msg = f"touched {len(extra)} file(s) outside scope (within tolerance): {', '.join(extra)}" if extra else ""
        if new_tests:
            msg = (msg + "; " if msg else "") + f"added new test files: {', '.join(new_tests)}"
        return True, msg, extra

    def task_tests(self, task: dict) -> list[str]:
        refs = set(task["acceptance_checks"])
        for e in self.progress.tasks:
            if e["status"] == "done":
                refs |= set(next(t for t in self.plan["tasks"] if t["id"] == e["id"])["acceptance_checks"])
        files = []
        for f in sorted(self.lock.checksums):
            fp = self.repo / f
            if fp.exists() and any(r in fp.read_text(encoding="utf-8", errors="ignore") for r in refs):
                files.append(f)
        new = [f for f in self.git.changed_files(self.last_good_commit())
               if self.lock.matches(f) and f not in self.lock.checksums and not self.is_managed(f)]
        return files + new

    def final_checks(self) -> None:
        if any(t["status"] != "done" for t in self.progress.tasks):
            return
        ok, errors, results = run_checks(self.cfg, self.repo)
        self.progress.check_results = results
        self.progress.final_checks_passed = ok
        if not ok:
            self.progress.warnings.append("FINAL full-suite checks FAILED after all tasks passed individually: " + self.summarize(errors))
            self.log("final full-suite checks failed")

    def run_diff_exceeded(self) -> bool:
        total = sum((t["diff"] or {}).get("added", 0) + (t["diff"] or {}).get("removed", 0) for t in self.progress.tasks if t.get("diff"))
        return total > self.cfg["guardrails"]["diff_cap_lines_per_run"]

    def mark(self, entry: dict, status: str, reason: Optional[str] = None) -> None:
        entry["status"] = status
        entry["blocked_reason"] = reason if status == "blocked" else None
        if status == "blocked":
            self.log(f"{entry['id']} BLOCKED: {reason}")

    @staticmethod
    def summarize(errors: Optional[str]) -> str:
        if not errors:
            return "no attempts made"
        lines = [l for l in errors.splitlines() if l.strip() and not l.startswith("###")]
        return " | ".join(lines[:3])[:400]

    # ------------------------------------------------------------------ rollback
    def rollback(self, task_id: str) -> None:
        self.progress = Progress.load(self.progress_path)
        plan_path = self.sdir() / "plan.json"
        self.plan = json.loads((plan_path if plan_path.exists() else self.lay.plan_json(self.feature)).read_text(encoding="utf-8"))
        if self.git.is_dirty():
            raise PreflightError("working tree is dirty; refusing to rollback")
        dependents = set()

        def collect(tid: str) -> None:
            for t in self.plan["tasks"]:
                if tid in t["depends_on"] and t["id"] not in dependents:
                    dependents.add(t["id"])
                    collect(t["id"])

        collect(task_id)
        targets = [task_id] + [t["id"] for t in self.progress.tasks if t["id"] in dependents]
        done_entries = [self.progress.task(t) for t in targets if self.progress.task(t)["status"] == "done"]
        for e in reversed(done_entries):
            if not self.git.revert(e["commit"]):
                raise RuntimeError(f"revert of {e['id']} ({e['commit'][:8]}) conflicted; resolve manually")
            self.log(f"reverted {e['id']} ({e['commit'][:8]})")
        for t in targets:
            e = self.progress.task(t)
            e.update({"status": "pending", "attempts": 0, "commit": None, "blocked_reason": None, "diff": None})
        self.progress.stop_reason = "rolled_back"
        self.progress.save(self.progress_path)
        self.write_report()
        self.commit_state()

    # ------------------------------------------------------------------ report
    def write_report(self) -> Path:
        p = self.progress
        out = self.report_path
        out.parent.mkdir(parents=True, exist_ok=True)
        done = [t for t in p.tasks if t["status"] == "done"]
        blocked = [t for t in p.tasks if t["status"] == "blocked"]
        pending = [t for t in p.tasks if t["status"] in ("pending", "in_progress")]
        L = [f"# Report — {p.feature}", "", f"- Run `{p.run_id}` on branch `{p.branch}`",
             f"- Stop reason: **{p.stop_reason or 'running'}**{(' — ' + p.stop_detail) if p.stop_detail else ''}",
             f"- Tasks: {len(done)} done, {len(blocked)} blocked, {len(pending)} pending", ""]
        L += ["## 1. Assumptions (read these first)"]
        dec = self.decisions_text()
        L += [dec.strip() if "## D-" in dec else "_No assumptions logged — the spec answered everything the loop hit._", ""]
        L += ["## 2. Blocked tasks"]
        L += [f"- **{t['id']}** {t['title']} — {t['blocked_reason']} (attempts: {t['attempts']})" for t in blocked] or ["_None._"]
        L += ["", "## 3. Completed tasks"]
        L += [f"- **{t['id']}** {t['title']} — `{(t['commit'] or '')[:8]}`" for t in done] or ["_None._"]
        if pending:
            L += ["", "## 3b. Pending (not attempted / interrupted)"] + [f"- **{t['id']}** {t['title']}" for t in pending]
        L += ["", "## 4. Check results" + (" — final full suite" if p.final_checks_passed is not None else " (last task)")]
        L += [f"- {c['name']}: {'PASS' if c['passed'] else 'FAIL'} ({c['seconds']}s)" for c in p.check_results] or ["_No checks run._"]
        L += ["", "## 5. Diff stats"]
        L += [f"- {t['id']}: {t['diff']['files']} files, +{t['diff']['added']}/-{t['diff']['removed']}" for t in done if t.get("diff")] or ["_None._"]
        b = p.budget
        L += ["", "## 6. Budget", f"- Agent calls for implementation: {b.get('iterations_used', 0)} / {self.cfg['budget']['max_iterations']}",
              f"- Wall-clock: {b.get('elapsed_min', 0)} min / {self.cfg['budget']['wall_clock_seconds'] // 60} min"]
        if b.get("cost_usd"):
            L += [f"- Cost reported by the harness: ${b['cost_usd']:.2f} (all loop calls)"]
            if b.get("cost_by_role"):
                L += ["  - by role: " + ", ".join(f"{r} ${v:.2f}" for r, v in sorted(b["cost_by_role"].items(), key=lambda x: -x[1]))]
        i = p.infra or {}
        L += ["", "## 7. Infrastructure", f"- Harness: {i.get('harness', '?')}",
              f"- Transient agent failures: {i.get('transient_failures', 0)}",
              f"- Time lost to outages: {i.get('total_outage_minutes', 0)} min", f"- Circuit breaker tripped: {i.get('breaker_tripped', False)}"]
        L += ["", "## 8. Critic rejections"]
        rej = [(c["round"], v) for c in p.critique for v in c["verdicts"] if v["verdict"] != "accept"]
        L += [f"- round {r}: {v['critic']}: " + "; ".join(v["issues"]) for r, v in rej] or ["_None._"]
        L += ["", "## 9. Warnings"] + ([f"- {w}" for w in p.warnings] or ["_None._"])
        L += ["", "## 10. Next steps", "",
              f"- Wrong assumption? `semipilot rollback {p.feature} T<n>` then fix the spec and `semipilot resume {p.feature}`",
              f"- Blocked or interrupted? answer in the spec / decisions, then `semipilot resume {p.feature}`",
              "- Happy? review the diff" + (", run the semipilot-scribe skill with implementation-plan.md (cards, ADRs, changelog)" if self.kl else "")
              + ", then open the PR yourself (the loop never pushes). Draft below.", ""]
        L += ["## 11. PR description draft", "", f"### {p.feature}", ""]
        if self.plan:
            L += [f"- {t['title']}" for t in self.plan["tasks"] if self.progress.task(t["id"])["status"] == "done"]
        L += ["", f"Requirements: `{self.spec_rel}` · Plan: `{self.lay.rel(self.lay.implementation_plan(self.feature))}` · Decisions: `{self.decisions_rel}`", "",
              f"Per-call logs: `{self.lay.rel(self.lay.runs)}/{p.run_id}/`", ""]
        out.write_text("\n".join(L), encoding="utf-8")
        return out
