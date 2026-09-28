"""Copilot CLI runner for the PilotInLoop loop.

Responsibilities (handoff §4.2, §4.3, §4.6):
- one fresh `copilot -p ...` process per call; refuses resume/continue flags
- per-call timeout and logging (prompt, stdout, stderr, exit code, duration)
- failure classification: ok | task_failure | transient | fatal | quota_exhausted | unknown
- retry with exponential backoff + jitter for transient failures
- circuit breaker on continuous / total outage
- raises HaltRun for fatal / quota / breaker so the orchestrator can stop cleanly

The interface is deliberately small so the runner can be swapped:
    runner.run(role, prompt, attempt_label) -> CallResult
"""
from __future__ import annotations

import json
import os
import random
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

OK = "ok"
TASK_FAILURE = "task_failure"
TRANSIENT = "transient"
FATAL = "fatal"
QUOTA = "quota_exhausted"
UNKNOWN = "unknown"

HARD_FORBIDDEN_FLAGS = ("--resume", "--continue", "--session-id")


class HaltRun(Exception):
    """Raised when the run must stop. `reason` is one of the stop reasons in §9."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class ForbiddenFlagError(ValueError):
    pass


@dataclass
class CallResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    kind: str = OK
    log_path: Optional[str] = None
    command: list[str] = field(default_factory=list)

    @property
    def combined(self) -> str:
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


def classify(result: CallResult, patterns: dict) -> str:
    """Classify a CLI outcome. Timeouts are task failures (the orchestrator decides what to do)."""
    if result.timed_out:
        return TASK_FAILURE
    if result.exit_code == 0:
        return OK
    text = f"exit={result.exit_code}\n{result.combined}"
    for kind in (FATAL, QUOTA, TRANSIENT):
        for pat in patterns.get(kind, []):
            if re.search(pat, text, re.IGNORECASE):
                return kind
    return UNKNOWN


def _parse_retry_after(text: str) -> Optional[float]:
    m = re.search(r"retry[- ]after[:=\s]+(\d+)", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


class CopilotRunner:
    def __init__(
        self,
        config: dict,
        log_dir: Path,
        sleep_fn: Callable[[float], None] = time.sleep,
        reset_tree_fn: Optional[Callable[[], None]] = None,
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
    ):
        self.cfg = config
        self.rcfg = config["runner"]
        self.icfg = config["infra"]
        self.patterns = config.get("failure_patterns", {})
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
        self.calls: list[dict] = []
        self._unknown_seen: set[str] = set()

    # ------------------------------------------------------------------ command
    def build_command(self, role: str, prompt: str, extra: Optional[list[str]] = None) -> list[str]:
        r = self.rcfg
        cmd = shlex.split(r["command"]) if isinstance(r["command"], str) else list(r["command"])
        cmd += ["-p", prompt, "-s", "--no-ask-user"]
        if r.get("model"):
            cmd += ["--model", str(r["model"])]
        agent = (r.get("agents") or {}).get(role)
        if agent:
            cmd += ["--agent", str(agent)]
        for tool in (r.get("allow_tools") or {}).get(role, []) or []:
            cmd += [f"--allow-tool={tool}"]
        for tool in r.get("deny_tools") or []:
            cmd += [f"--deny-tool={tool}"]
        cmd += ["--log-dir", str(self.log_dir / "cli")]
        cmd += list(r.get("extra_flags") or [])
        cmd += list(extra or [])
        self._guard(cmd)
        return cmd

    def _guard(self, cmd: list[str]) -> None:
        forbidden = set(HARD_FORBIDDEN_FLAGS) | set(self.rcfg.get("forbidden_flags") or [])
        for arg in cmd[1:]:
            if arg in ("-p",):
                continue
            for f in forbidden:
                if arg == f or arg.startswith(f + "="):
                    raise ForbiddenFlagError(
                        f"refusing to build a command line containing {f!r}: one fresh session per call is a hard requirement"
                    )

    # ------------------------------------------------------------------ invoke
    def invoke(self, role: str, prompt: str, attempt_label: str, extra: Optional[list[str]] = None) -> CallResult:
        cmd = self.build_command(role, prompt, extra)
        timeout = float(self.rcfg["call_timeout_seconds"])
        log_path = self.log_dir / f"{attempt_label}.log"
        t0 = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=self.cwd, env=self.env,
                stdin=subprocess.DEVNULL,
            )
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            code = -9
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        dur = time.monotonic() - t0
        res = CallResult(exit_code=code, stdout=out, stderr=err, duration_s=dur, timed_out=timed_out,
                         log_path=str(log_path), command=cmd)
        res.kind = classify(res, self.patterns)
        self._write_log(log_path, role, prompt, res)
        self.calls.append({"label": attempt_label, "role": role, "kind": res.kind, "exit": code,
                           "duration_s": round(dur, 1), "timed_out": timed_out})
        return res

    def _write_log(self, path: Path, role: str, prompt: str, res: CallResult) -> None:
        redacted = [a if not a.startswith("-p") else a for a in res.command]
        body = [
            f"# role: {role}", f"# kind: {res.kind}", f"# exit: {res.exit_code}",
            f"# duration_s: {res.duration_s:.1f}", f"# timed_out: {res.timed_out}",
            f"# command: {' '.join(shlex.quote(a) for a in redacted if a != prompt)}",
            "", "## PROMPT", prompt, "", "## STDOUT", res.stdout, "", "## STDERR", res.stderr,
        ]
        path.write_text("\n".join(body))

    # ------------------------------------------------------------------ retry policy
    def run(self, role: str, prompt: str, attempt_label: str, extra: Optional[list[str]] = None) -> CallResult:
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
                raise HaltRun("copilot_unavailable", f"outage breaker tripped after {self.outage.transient_count} transient failures")
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
                return json.loads(c)
            except json.JSONDecodeError:
                continue
        return None


def _jitter(delay: float) -> float:
    return delay * random.uniform(0.8, 1.2)


def _tail(text: str, n: int = 20) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])
