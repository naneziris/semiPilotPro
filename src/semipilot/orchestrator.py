"""The semipilot loop: plan → critique → locked tests → implement task by task → checks → report.

The orchestrator owns the loop. The agent never decides that work is done: done == all configured checks pass.
Humans sit at the front (requirements, Gate 1 approval, answered questions) and at the back (report review).

Layout inside a repo (see config.Layout):
    .semipilot/config.yaml                 the only file a user edits
    .semipilot/features/<slug>/requirements.md        written by /refine-requirements (@refiner), approved after
                                                      /spec-critic (frontmatter status: approved) — the human gate
    .semipilot/features/<slug>/open-questions.md      planner's questions, answered inline by the human
    .semipilot/features/<slug>/implementation-plan.md the accepted plan, rendered for humans and for @scribe
    .semipilot/features/<slug>/decisions.md           assumptions the loop made (read these first in the morning)
    .semipilot/features/<slug>/rejection-log.md       critic rejections
    .semipilot/features/<slug>/report.md              the morning report
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
import subprocess
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Optional

from .config import Layout, knowledge_layer_present
from .runner import OK, CopilotRunner, HaltRun


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
    def __init__(self, repo: Path):
        self.repo = Path(repo)

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

    def checkout(self, name: str) -> None:
        self.run("checkout", "-q", name)

    def changed_files(self, base: str) -> list[str]:
        tracked = self.run("diff", "--name-only", base).splitlines()
        untracked = self.run("ls-files", "--others", "--exclude-standard").splitlines()
        return sorted(set(f for f in tracked + untracked if f))

    def diff_lines(self, base: str, paths: Optional[list[str]] = None, exclude: Optional[list[str]] = None) -> tuple[int, int]:
        self.run("add", "-N", "--all")
        args = ["diff", "--numstat", base]
        if paths or exclude:
            args += ["--", *(paths or ["."]), *[f":(exclude){e.rstrip('/')}" for e in (exclude or [])]]
        out = self.run(*args)
        self.run("reset", "-q")
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
            if subprocess.run(["git", "cat-file", "-e", f"{sha}:{p}"], cwd=self.repo, capture_output=True).returncode == 0:
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
        self.run("commit", "-q", "-m", message)
        return self.head()

    def revert(self, sha: str) -> bool:
        r = subprocess.run(["git", "revert", "--no-edit", sha], cwd=self.repo, capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "revert", "--abort"], cwd=self.repo, capture_output=True)
            return False
        return True

    def stat_between(self, a: str, b: str) -> dict:
        out = self.run("diff", "--numstat", a, b)
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

        for e in jsonschema.Draft202012Validator(load_schema()).iter_errors(plan):
            errors.append(f"schema: {'/'.join(str(p) for p in e.absolute_path)}: {e.message}")
    except ImportError:
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
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def parse_acceptance_criteria(text: str, tag_regex: str) -> tuple[list[dict], list[str]]:
    """Criteria live under a heading containing 'acceptance'. Each must carry `[check: <ref>]`."""
    tag = re.compile(tag_regex, re.IGNORECASE)
    criteria, untagged = [], []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            in_section = "acceptance" in line.lower()
            continue
        if not in_section or not re.match(r"^([-*]|\d+[.)])\s+", line):
            continue
        body = re.sub(r"^([-*]|\d+[.)])\s+", "", line)
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
            out = (r.stdout + "\n" + r.stderr).strip().splitlines()
            errors.append(f"### check `{chk['name']}` failed (`{cmd}`)\n" + "\n".join(out[-tail:]))
            break
    return ok, "\n\n".join(errors), results


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
def load_prompt(name: str, override_dir: Optional[Path] = None) -> str:
    if override_dir and (override_dir / f"{name}.md").exists():
        return (override_dir / f"{name}.md").read_text(encoding="utf-8")
    return resources.files("semipilot").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")


def render_prompt(name: str, override_dir: Optional[Path] = None, **kw) -> str:
    template = load_prompt(name, override_dir)

    class Safe(dict):
        def __missing__(self, k):
            return "{" + k + "}"

    return template.format_map(Safe(**{k: (v if isinstance(v, str) else json.dumps(v, indent=2)) for k, v in kw.items()}))


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
        self.runner: Optional[CopilotRunner] = None
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

    def make_runner(self) -> CopilotRunner:
        self.runner = CopilotRunner(self.cfg, self.run_dir(), sleep_fn=self.sleep, cwd=self.repo,
                                    reset_tree_fn=lambda: self.reset_tree("infra failure"))
        return self.runner

    def prompt(self, name: str, **kw) -> str:
        return render_prompt(name, self.lay.custom_prompts, **kw)

    def last_good_commit(self) -> str:
        done = [t["commit"] for t in self.progress.tasks if t["status"] == "done" and t.get("commit")]
        return done[-1] if done else (self.progress.tests_commit or self.progress.base_commit)

    def reset_tree(self, why: str) -> None:
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
        return f"{self.cfg['git']['branch_prefix']}{self.feature}-{self.now().strftime('%Y%m%d')}"

    def ensure_gitignore(self) -> None:
        gi = self.lay.root / ".gitignore"
        self.lay.root.mkdir(parents=True, exist_ok=True)
        if not gi.exists() or "runs/" not in gi.read_text(encoding="utf-8"):
            with open(gi, "a", encoding="utf-8") as f:
                f.write("runs/\nlast-run\n")

    # ------------------------------------------------------------------ preflight
    def check_spec(self) -> list[dict]:
        if not self.spec_path.exists():
            raise PreflightError(f"{self.spec_rel} not found. In Copilot chat run `/refine-requirements <your idea>`, then `/spec-critic`.")
        text = self.spec_text()
        fm = parse_frontmatter(text)
        if str(fm.get("status", "")).lower() != "approved":
            raise PreflightError(f"{self.spec_rel} is not approved. Run `/spec-critic` in Copilot chat and reply `approve` "
                                 "(or set `status: approved` in its frontmatter yourself).")
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
        cmd = self.cfg["knowledge_layer"]["validate_cmd"]
        r = subprocess.run(cmd, shell=True, cwd=self.repo, capture_output=True, text=True)
        if r.returncode != 0:
            raise PreflightError(f"knowledge layer unhealthy (`{cmd}` failed) — fix the cards before a run:\n{(r.stdout + r.stderr)[-1500:]}")
        self.log("knowledge layer healthy")

    def tags(self) -> list[str]:
        """Tags from `requirements.md > Knowledge References > Tags:` — the retrieval key for the knowledge layer."""
        m = re.search(r"^\s*[-*]?\s*\**Tags\**\s*:\s*(.+)$", self.spec_text(), re.MULTILINE | re.IGNORECASE)
        if not m:
            return []
        return [t.strip().strip("`") for t in re.split(r"[,\s]+", m.group(1)) if t.strip().strip("`")]

    def kl_context(self) -> dict:
        """Prompt variables describing how to retrieve module knowledge."""
        if self.kl:
            tags = self.tags()
            resolve = self.cfg["knowledge_layer"]["resolve_cmd"].replace("{tags}", ",".join(tags) or "<tags>")
            return {"knowledge": (
                "This repository has a knowledge layer. Module knowledge comes from it, not from grepping: run "
                f"`{resolve}` and read ONLY the cards (and the deep docs they link) it returns; open code only inside "
                "those cards' `code:` paths. Honor every card's `invariants:` and `public_contracts:`. Never modify "
                "`docs/cards/`, `AGENTS.md`, `.github/copilot-instructions.md` or `.github/instructions/` — `@scribe` "
                "does that after the human review."
                + ("" if tags else " (requirements.md lists no tags under Knowledge References — pick 1–4 from "
                   "`docs/cards/_vocabulary.md` yourself and say which.)")),
                "knowledge_updates_rule": (
                    "Also output `knowledge_updates`: one line per card owning a changed file (`docs/cards/<card>.md: "
                    "<delta or 'no change'>`), plus `.github/instructions/<area>.instructions.md`, `docs/decisions.md` "
                    "(ADR title or 'no change'), `docs/dependencies.md`, and the `docs/CHANGELOG.md` line. "
                    "@scribe executes this list after the human review; the loop never touches those files.")}
        return {"knowledge": (
            "Follow the repository's instructions: `.github/copilot-instructions.md`, `AGENTS.md`, and any "
            "`.github/instructions/*.instructions.md` whose `applyTo` matches the files involved. Never modify them."),
            "knowledge_updates_rule": "`knowledge_updates` may be omitted (no knowledge layer in this repository)."}

    def render_implementation_plan(self) -> None:
        """implementation-plan.md: the plan in the manual pipeline's vocabulary, for the human and for @scribe."""
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
              "What `@scribe` must update after the human review (the loop never touches these files):", ""]
        L += [f"- {k}" for k in self.plan.get("knowledge_updates") or []] or ["- (planner listed none" + (" — check the cards owning the changed files)" if self.kl else ")")]
        L += [""]
        self.lay.implementation_plan(self.feature).write_text("\n".join(L), encoding="utf-8")

    def check_config(self) -> None:
        if not self.cfg.get("checks"):
            raise PreflightError("no `checks` configured in .semipilot/config.yaml (run `semipilot init`, then edit)")
        for chk in self.cfg["checks"]:
            if str(chk.get("cmd", "")).lstrip().startswith("#"):
                raise PreflightError(f"check `{chk.get('name')}` is still a TODO in .semipilot/config.yaml")

    def commit_feature_files(self, what: str) -> None:
        """If the only uncommitted files are this feature's own Markdown (spec, answers), commit them —
        that is the human's gate work, and asking them to git-add it is a papercut."""
        feat_rel = self.lay.rel(self.lay.feature_dir(self.feature)) + "/"
        dirty = [l[3:] for l in self.git.run("status", "--porcelain").splitlines() if l.strip()]
        if dirty and all(f.startswith(feat_rel) or f.startswith(self.lay.rel(self.lay.root) + "/.gitignore") for f in dirty):
            self.git.run("add", "-A", "--", feat_rel, self.lay.rel(self.lay.root / ".gitignore"))
            self.git.run("commit", "-q", "-m", f"{self.cfg['git']['commit_prefix']} {self.feature}: {what}")
            self.log(f"committed {feat_rel} ({what})")

    def check_tree(self) -> None:
        self.commit_feature_files("spec and answers")
        if self.git.is_dirty():
            raise PreflightError("working tree is dirty; commit or stash before a run")
        if self.git.branch_exists(self.branch_name()):
            raise PreflightError(f"branch {self.branch_name()} already exists; delete it or wait a day (the date is in the name)")

    def check_copilot(self) -> None:
        res = self.runner.invoke("health", self.cfg["preflight"]["health_prompt"], "health")
        if res.kind != OK:
            raise PreflightError(f"Copilot CLI health check failed ({res.kind}, exit {res.exit_code}). Run `copilot login`?\n{res.combined[-1500:]}")
        pf = self.cfg["preflight"]
        if pf.get("auth_check_cmd"):
            r = subprocess.run(pf["auth_check_cmd"], shell=True, cwd=self.repo, capture_output=True, text=True)
            if r.returncode != 0:
                raise PreflightError(f"auth check `{pf['auth_check_cmd']}` failed:\n{(r.stdout + r.stderr)[-1500:]}")
        exp_env = pf.get("token_expiry_env")
        if exp_env and os.environ.get(exp_env):
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
        text = res.stdout.strip() + "\n"
        self.questions_path.parent.mkdir(parents=True, exist_ok=True)
        self.questions_path.write_text(text, encoding="utf-8")
        n, _ = parse_questions(text)
        return n

    # ------------------------------------------------------------------ run
    def run(self, skip_questions: bool = False, preflight_only: bool = False) -> str:
        """Full run. Raises NeedsAnswers when the human has questions to answer first.
        `preflight_only` stops after the checks and the questions (the evening step)."""
        self.ensure_gitignore()
        self.check_config()
        crit = self.check_spec()
        self.check_knowledge_layer()
        self.check_tree()
        self.log(f"{self.feature}: {len(crit)} tagged acceptance criteria, requirements approved, tree clean")

        # temporary progress for the preflight logs
        pre_id = f"preflight-{self.feature}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        self.progress = Progress(run_id=pre_id, feature=self.feature, branch=self.branch_name(),
                                 started_at=self.now().isoformat(), base_commit=self.git.head())
        self.make_runner()
        self.check_copilot()
        self.log("Copilot CLI OK")

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
        self.log(f"run {run_id} on branch {branch}")
        try:
            self.stage_plan(crit)
            self.stage_tests(crit)
            self.stage_implement()
            self.progress.stop_reason = self.progress.stop_reason or "completed"
        except HaltRun as h:
            self.on_halt(h)
        finally:
            self.finish()
        return self.progress.stop_reason

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
        if not self.progress_path.exists():
            raise PreflightError(f"nothing to resume for '{self.feature}' (no progress.json)")
        self.progress = Progress.load(self.progress_path)
        if self.git.current_branch() != self.progress.branch:
            self.git.checkout(self.progress.branch)
        self.progress.budget["elapsed_min_before_resume"] = self.progress.budget.get("elapsed_min", 0)
        self.progress.stop_reason = None
        self.lock.from_json(self.progress.test_lock)
        plan_path = self.sdir() / "plan.json"
        if not plan_path.exists():
            copy = self.lay.plan_json(self.feature)
            if copy.exists():
                plan_path.write_text(copy.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                raise PreflightError(f"plan.json missing at {plan_path}")
        self.plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.make_runner()
        if self.git.is_dirty():
            self.reset_tree("resume with dirty tree")
        for t in self.progress.tasks:
            if t["status"] == "in_progress":
                t["status"] = "pending"
        try:
            self.stage_implement()
            self.progress.stop_reason = self.progress.stop_reason or "completed"
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
        self.ensure_gitignore()
        paths = [m for m in self.managed() if (self.repo / m.rstrip("/")).exists() and not m.endswith("runs/")]
        paths.append(self.lay.rel(self.lay.root / ".gitignore"))
        self.git.run("add", "-A", "--", *paths)
        if self.git.run("diff", "--cached", "--name-only").strip():
            self.git.run("commit", "-q", "-m", f"{self.cfg['git']['commit_prefix']} state: {self.progress.stop_reason or 'update'}")

    def maybe_schedule_retry(self) -> None:
        win = self.cfg["infra"].get("retry_window")
        if not win or self.progress.stop_reason != "copilot_unavailable":
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
            plan = CopilotRunner.extract_json(res.stdout)
            errors = validate_plan(plan, self.cfg, crit) if plan else ["no JSON object found in planner output"]
            if not errors:
                return plan
            self.log(f"plan attempt {attempt} invalid: {errors}")
            rejections = (rejections + "\n\n### Schema/sizing validation errors\n" + "\n".join(f"- {e}" for e in errors)).strip()
        raise HaltRun("plan_rejected", "planner could not produce a valid plan in 2 attempts")

    def call_critics(self, plan: dict, rnd: int) -> list[dict]:
        out = []
        for critic in ("spec-critic", "plan-critic"):
            prompt = self.prompt(critic, plan_json=plan, spec_path=self.spec_rel, questions_path=self.questions_rel,
                                 max_files=self.cfg["guardrails"]["max_expected_files_per_task"], **self.kl_context())
            res = self.runner.run(critic, prompt, f"{critic}-round{rnd + 1}")
            v = CopilotRunner.extract_json(res.stdout) or {"verdict": "reject", "issues": ["critic returned no JSON verdict"]}
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
        self.runner.run("test-writer", prompt, "test-writer")
        changed = [f for f in self.git.changed_files(self.progress.base_commit) if not self.is_managed(f)]
        non_test = [f for f in changed if not self.lock.matches(f)]
        if non_test:
            self.git.restore_paths(self.progress.base_commit, non_test)
            self.progress.warnings.append(f"test-writer touched non-test files, reverted: {', '.join(non_test)}")
        self.lock.lock()
        sha = self.git.commit(f"{self.cfg['git']['commit_prefix']} tests: locked acceptance tests", exclude=self.managed())
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
                sha = self.git.commit(f"{self.cfg['git']['commit_prefix']} {task['id']}: {task['title']}", exclude=self.managed())
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
                        sha = self.git.commit(f"{self.cfg['git']['commit_prefix']} {task['id']}: {task['title']}", exclude=self.managed())
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
        L += ["", "## 6. Budget", f"- Copilot calls for implementation: {b.get('iterations_used', 0)} / {self.cfg['budget']['max_iterations']}",
              f"- Wall-clock: {b.get('elapsed_min', 0)} min / {self.cfg['budget']['wall_clock_seconds'] // 60} min"]
        i = p.infra or {}
        L += ["", "## 7. Infrastructure", f"- Transient Copilot failures: {i.get('transient_failures', 0)}",
              f"- Time lost to outages: {i.get('total_outage_minutes', 0)} min", f"- Circuit breaker tripped: {i.get('breaker_tripped', False)}"]
        L += ["", "## 8. Critic rejections"]
        rej = [(c["round"], v) for c in p.critique for v in c["verdicts"] if v["verdict"] != "accept"]
        L += [f"- round {r}: {v['critic']}: " + "; ".join(v["issues"]) for r, v in rej] or ["_None._"]
        L += ["", "## 9. Warnings"] + ([f"- {w}" for w in p.warnings] or ["_None._"])
        L += ["", "## 10. Next steps", "",
              f"- Wrong assumption? `semipilot rollback {p.feature} T<n>` then fix the spec and `semipilot resume {p.feature}`",
              f"- Blocked or interrupted? answer in the spec / decisions, then `semipilot resume {p.feature}`",
              "- Happy? review the diff" + (", run `@scribe` with implementation-plan.md (cards, ADRs, changelog)" if self.kl else "")
              + ", then open the PR yourself (the loop never pushes). Draft below.", ""]
        L += ["## 11. PR description draft", "", f"### {p.feature}", ""]
        if self.plan:
            L += [f"- {t['title']}" for t in self.plan["tasks"] if self.progress.task(t["id"])["status"] == "done"]
        L += ["", f"Requirements: `{self.spec_rel}` · Plan: `{self.lay.rel(self.lay.implementation_plan(self.feature))}` · Decisions: `{self.decisions_rel}`", "",
              f"Per-call logs: `{self.lay.rel(self.lay.runs)}/{p.run_id}/`", ""]
        out.write_text("\n".join(L), encoding="utf-8")
        return out
