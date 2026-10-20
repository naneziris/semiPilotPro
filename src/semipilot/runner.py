"""Agent runner for the PilotInLoop loop — harness-agnostic.

Responsibilities (handoff §4.2, §4.3, §4.6):
- one fresh agent process per call, built by the configured harness adapter (`harness.py`); session/resume and
  permission-bypass flags are refused
- per-call timeout and logging (prompt, stdout, stderr, exit code, duration, cost when the harness reports it)
- failure classification: ok | task_failure | transient | fatal | quota_exhausted | unknown
- retry with exponential backoff + jitter for transient failures
- circuit breaker on continuous / total outage
- raises HaltRun for fatal / quota / breaker so the orchestrator can stop cleanly

The interface is deliberately small:
    runner.run(role, prompt, attempt_label) -> CallResult      (CallResult.text is the agent's answer)
"""
from __future__ import annotations

import json
import random
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .harness import ForbiddenFlagError, Harness, get_harness, role_profile  # noqa: F401  (re-exported)

OK = "ok"
TASK_FAILURE = "task_failure"
TRANSIENT = "transient"
FATAL = "fatal"
QUOTA = "quota_exhausted"
UNKNOWN = "unknown"

AGENT_UNAVAILABLE = "agent_unavailable"


class HaltRun(Exception):
    """Raised when the run must stop. `reason` is one of the stop reasons in §9."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass
class CallResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    kind: str = OK
    log_path: Optional[str] = None
    command: list = field(default_factory=list)
    text: str = ""            # the agent's answer (stdout for plain-text CLIs, `result` for JSON ones)
    meta: dict = field(default_factory=dict)

    @property
    def combined(self) -> str:
        """The text failure patterns are matched against. For a JSON-speaking harness that is the answer, its error
        list and stderr — never the raw JSON, whose telemetry numbers (`ttft_ms: 429`, …) would match status codes."""
        if self.meta:
            errs = self.meta.get("errors")
            return "\n".join(x for x in (self.text, errs if isinstance(errs, str) else "", self.stderr) if x)
        return f"{self.stdout}\n{self.stderr}"


@dataclass
class OutageTracker:
    """Tracks time lost to transient infra failures (§4.6 circuit breaker)."""

    max_continuous_s: float
    max_total_s: float
    continuous_s: float = 0.0
    total_s: float = 0.0
    transient_count: int = 0
    breaker_tripped: bool = False

    def add_wait(self, seconds: float) -> None:
        self.transient_count += 1
        self.continuous_s += seconds
        self.total_s += seconds

    def clear_continuous(self) -> None:
        self.continuous_s = 0.0

    def tripped(self) -> bool:
        if self.continuous_s > self.max_continuous_s or self.total_s > self.max_total_s:
            self.breaker_tripped = True
        return self.breaker_tripped

    def summary(self) -> dict:
        return {
            "transient_failures": self.transient_count,
            "total_outage_minutes": round(self.total_s / 60, 1),
            "breaker_tripped": self.breaker_tripped,
        }


def match_patterns(text: str, patterns: dict) -> Optional[str]:
    for kind in (FATAL, QUOTA, TRANSIENT):
        for pat in patterns.get(kind, []):
            if re.search(pat, text, re.IGNORECASE):
                return kind
    return None


def classify(result: CallResult, patterns: dict, harness: Optional[Harness] = None) -> str:
    """Classify a CLI outcome. Timeouts are task failures (the orchestrator decides what to do).

    A zero exit is OK unless the harness itself reports an error (`meta.is_error`, e.g. Claude Code's JSON result);
    such an error is classified by the patterns, and counts as a task failure when none match (max turns etc.)."""
    if result.timed_out:
        return TASK_FAILURE
    if result.exit_code == 0 and not result.meta.get("is_error"):
        return OK
    structured = harness.classify_meta(result.meta) if harness else None
    if structured:
        return structured
    text = f"exit={result.exit_code}\n{result.combined}"
    kind = match_patterns(text, patterns)
    if kind:
        return kind
    return TASK_FAILURE if result.exit_code == 0 else UNKNOWN


def _parse_retry_after(text: str) -> Optional[float]:
    m = re.search(r"retry[- ]after[:=\s]+(\d+)", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


class Runner:
    def __init__(
        self,
        config: dict,
        log_dir: Path,
        sleep_fn: Callable[[float], None] = time.sleep,
        reset_tree_fn: Optional[Callable[[], None]] = None,
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        harness: Optional[Harness] = None,
    ):
        self.cfg = config
        self.rcfg = config["runner"]
        self.icfg = config["infra"]
        self.harness = harness or get_harness(config)
        self.patterns = self.harness.failure_patterns()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep_fn
        self.reset_tree = reset_tree_fn or (lambda: None)
        self.cwd = cwd
        self.env = env
        self.outage = OutageTracker(
            max_continuous_s=float(self.icfg["max_outage_seconds"]),
            max_total_s=float(self.icfg["max_total_outage_seconds"]),
        )
        self.calls: list = []
        self.cost_usd: float = 0.0
        self.cost_by_role: dict = {}
        self._unknown_seen: set = set()

    # ------------------------------------------------------------------ command
    def build(self, role: str, prompt: str, extra: Optional[list] = None):
        profile = role_profile(self.cfg, role)
        return self.harness.command(role, profile, prompt, str(self.log_dir / "cli"), extra)

    def build_command(self, role: str, prompt: str, extra: Optional[list] = None) -> list:
        return self.build(role, prompt, extra).argv

    # ------------------------------------------------------------------ invoke
    def invoke(self, role: str, prompt: str, attempt_label: str, extra: Optional[list] = None) -> CallResult:
        inv = self.build(role, prompt, extra)
        timeout = float(self.rcfg["call_timeout_seconds"])
        log_path = self.log_dir / f"{attempt_label}.log"
        t0 = time.monotonic()
        timed_out = False
        stdin_kw = {"input": inv.stdin} if inv.stdin is not None else {"stdin": subprocess.DEVNULL}
        try:
            proc = subprocess.run(inv.argv, capture_output=True, text=True, timeout=timeout, cwd=self.cwd,
                                  env=self.env, **stdin_kw)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            code = -9
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        except FileNotFoundError:
            code, out, err = 127, "", f"{inv.argv[0]}: command not found — {self.harness.install_hint}"
        dur = time.monotonic() - t0
        text, meta = self.harness.response(out)
        res = CallResult(exit_code=code, stdout=out, stderr=err, duration_s=dur, timed_out=timed_out,
                         log_path=str(log_path), command=inv.argv, text=text, meta=meta)
        res.kind = classify(res, self.patterns, self.harness)
        cost = meta.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            self.cost_usd += float(cost)
            self.cost_by_role[role] = self.cost_by_role.get(role, 0.0) + float(cost)
        self._write_log(log_path, role, prompt, res)
        self.calls.append({"label": attempt_label, "role": role, "kind": res.kind, "exit": code,
                           "duration_s": round(dur, 1), "timed_out": timed_out,
                           **({"cost_usd": round(float(cost), 4)} if isinstance(cost, (int, float)) else {})})
        return res

    def _write_log(self, path: Path, role: str, prompt: str, res: CallResult) -> None:
        shown = [a for a in res.command if a != prompt]
        body = [
            f"# harness: {self.harness.name}", f"# role: {role} ({role_profile(self.cfg, role)})",
            f"# kind: {res.kind}", f"# exit: {res.exit_code}", f"# duration_s: {res.duration_s:.1f}",
            f"# timed_out: {res.timed_out}", f"# meta: {json.dumps(res.meta)}",
            f"# command: {' '.join(shlex.quote(a) for a in shown)}",
            "", "## PROMPT", prompt, "", "## ANSWER", res.text, "", "## STDOUT", res.stdout, "", "## STDERR", res.stderr,
        ]
        path.write_text("\n".join(body), encoding="utf-8")

    # ------------------------------------------------------------------ retry policy
    def run(self, role: str, prompt: str, attempt_label: str, extra: Optional[list] = None) -> CallResult:
        """Invoke with the §4.6 policy. Returns only ok / task_failure results; raises HaltRun otherwise.

        The task's attempt counter is owned by the orchestrator and is NOT affected by transient retries.
        """
        delay = float(self.icfg["backoff_start_seconds"])
        cap = float(self.icfg["backoff_cap_seconds"])
        infra_try = 0
        while True:
            label = attempt_label if infra_try == 0 else f"{attempt_label}-infra{infra_try}"
            res = self.invoke(role, prompt, label, extra)
            kind = res.kind
            if kind in (OK, TASK_FAILURE):
                self.outage.clear_continuous()
                return res
            if kind == FATAL:
                self.reset_tree()
                raise HaltRun("auth_failure", _tail(res.combined))
            if kind == QUOTA:
                self.reset_tree()
                raise HaltRun("quota_exhausted", _tail(res.combined))
            if kind == UNKNOWN:
                sig = _tail(res.combined, 3)
                if not self.icfg.get("unknown_as_transient_once", True) or sig in self._unknown_seen:
                    res.kind = TASK_FAILURE
                    return res
                self._unknown_seen.add(sig)
            # transient (or unknown-once): reset, wait, retry the same call
            self.reset_tree()
            wait = _parse_retry_after(res.combined) if kind == TRANSIENT else None
            wait = wait if wait is not None else _jitter(delay)
            self.outage.add_wait(wait)
            if self.outage.tripped():
                raise HaltRun(AGENT_UNAVAILABLE, f"{self.harness.label}: outage breaker tripped after "
                                                 f"{self.outage.transient_count} transient failures")
            self.sleep(wait)
            delay = min(delay * 2, cap)
            infra_try += 1

    # ------------------------------------------------------------------ helpers for parsing agent output
    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """Find the first JSON object in agent output (tolerates ``` fences and chatter)."""
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidates = [fenced.group(1)] if fenced else []
        start = text.find("{")
        if start != -1:
            candidates.append(text[start:text.rfind("}") + 1])
        for c in candidates:
            try:
                obj = json.loads(c)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        return None


# Backwards-compatible name (v0.1 imported CopilotRunner).
CopilotRunner = Runner


def _jitter(delay: float) -> float:
    return delay * random.uniform(0.8, 1.2)


def _tail(text: str, n: int = 20) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])
