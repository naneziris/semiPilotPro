"""What a loop call cost: time always, plus whatever the agent CLI reports.

Every call is measured the same way (role, wall-clock seconds). On top of that each harness reports what it can:

    Claude Code   total_cost_usd, tokens and API time in its JSON result
    Copilot CLI   premium requests, tokens per model and API time — either in the stats block it prints when it is
                  not run with --silent, or in the `session.shutdown` event of its session-state `events.jsonl`

A normalised usage record is a plain dict with any of these keys (a key is absent when the CLI did not report it):

    cost_usd, premium_requests, input_tokens, output_tokens, cached_tokens, api_seconds, model

`Ledger` adds the records up per role; its summary is what lands in implementation-progress.json (`budget.usage`)
and in the report, and `calls.jsonl` in the run folder keeps one line per call for anyone measuring the loop.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

NUMERIC = ("cost_usd", "premium_requests", "input_tokens", "output_tokens", "cached_tokens", "api_seconds")

# ----------------------------------------------------------------------------- Copilot CLI: the stats block
# Printed at exit unless --silent is given. Observed layout (github/copilot-cli):
#
#   Total usage est:        7 Premium requests
#   API time spent:         2m 59.626s
#   Total session time:     12m 15.77s
#   Total code changes:     +206 -77
#   Breakdown by AI model:
#    claude-sonnet-4.5       453.0k in, 13.1k out, 405.7k cached (Est. 7 Premium requests)
#
# Older builds print "Total duration (API)" and "Usage by model:" with "input, … output, … cache read".
_STATS_START = re.compile(r"^\s*Total usage est\w*\s*:", re.IGNORECASE | re.MULTILINE)
_PREMIUM = re.compile(r"Total usage est\w*\s*:\s*([\d.,]+)\s*Premium request", re.IGNORECASE)
_API_TIME = re.compile(r"(?:API time spent|Total duration \(API\))\s*:\s*([^\n]+)", re.IGNORECASE)
_MODEL_ROW = re.compile(
    r"^\s*(?P<model>[\w.\-:/]+)\s+(?P<inp>[\d.,]+[kKmM]?)\s*(?:in|input)\b[, ]+(?P<out>[\d.,]+[kKmM]?)\s*(?:out|output)\b"
    r"(?:[, ]+(?P<cached>[\d.,]+[kKmM]?)\s*(?:cached|cache read))?", re.MULTILINE)
_STATS_LINE = re.compile(r"^\s*(Total usage est|API time spent|Total session time|Total duration|Total code changes|"
                         r"Breakdown by AI model|Usage by model|Resume this session)", re.IGNORECASE)


def _num(text: str) -> float:
    """`453.0k` → 453000, `1.2M` → 1200000, `1,234` → 1234."""
    t = text.strip().replace(",", "")
    mult = 1.0
    if t[-1:] in "kK":
        mult, t = 1e3, t[:-1]
    elif t[-1:] in "mM":
        mult, t = 1e6, t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return 0.0


def _duration(text: str) -> float:
    """`2m 59.626s` / `1h 2m 3s` / `12.3s` → seconds."""
    total, found = 0.0, False
    for value, unit in re.findall(r"([\d.]+)\s*(h|ms|m|s)", text):
        found = True
        total += float(value) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if found else 0.0


def parse_copilot_stats(text: str) -> dict:
    """Usage from the stats block Copilot CLI prints at exit ({} when there is none in `text`)."""
    m = _STATS_START.search(text or "")
    if not m:
        return {}
    block = text[m.start():]
    out: dict = {}
    p = _PREMIUM.search(block)
    if p:
        out["premium_requests"] = _num(p.group(1))
    a = _API_TIME.search(block)
    if a and _duration(a.group(1)):
        out["api_seconds"] = round(_duration(a.group(1)), 1)
    models = []
    for row in _MODEL_ROW.finditer(block):
        models.append(row.group("model"))
        out["input_tokens"] = out.get("input_tokens", 0) + int(_num(row.group("inp")))
        out["output_tokens"] = out.get("output_tokens", 0) + int(_num(row.group("out")))
        if row.group("cached"):
            out["cached_tokens"] = out.get("cached_tokens", 0) + int(_num(row.group("cached")))
    if models:
        out["model"] = ", ".join(dict.fromkeys(models))
    return out


def strip_copilot_stats(text: str) -> str:
    """The agent's answer without the trailing stats block (used when the CLI is not run with --silent)."""
    m = _STATS_START.search(text or "")
    if not m:
        return text
    head, tail = text[:m.start()], text[m.start():]
    kept = []
    in_models = False
    for line in tail.splitlines():
        if _STATS_LINE.match(line):
            in_models = bool(re.match(r"^\s*(Breakdown by AI model|Usage by model)", line, re.IGNORECASE))
            continue
        if in_models and (_MODEL_ROW.match(line) or not line.strip()):
            continue
        in_models = False
        kept.append(line)
    rest = "\n".join(kept).strip()
    return (head.rstrip() + ("\n" + rest if rest else "")).rstrip() + ("\n" if text.endswith("\n") else "")


# ----------------------------------------------------------------------------- Copilot CLI: session-state events
def _shutdown_usage(data: dict) -> dict:
    out: dict = {}
    if isinstance(data.get("totalPremiumRequests"), (int, float)):
        out["premium_requests"] = float(data["totalPremiumRequests"])
    if isinstance(data.get("totalApiDurationMs"), (int, float)):
        out["api_seconds"] = round(float(data["totalApiDurationMs"]) / 1000, 1)
    metrics = data.get("modelMetrics")
    if isinstance(metrics, dict):
        models = []
        for model, m in metrics.items():
            if not isinstance(m, dict):
                continue
            models.append(str(model))
            u = m.get("usage") if isinstance(m.get("usage"), dict) else m
            for src, dst in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
                             ("cacheReadTokens", "cached_tokens")):
                if isinstance(u.get(src), (int, float)):
                    out[dst] = out.get(dst, 0) + int(u[src])
        if models:
            out["model"] = ", ".join(models)
    return out


def _session_files(root: Path) -> list[Path]:
    """Session event files: `<root>/<session-id>/events.jsonl` (current layout) or `<root>/<session-id>.jsonl`."""
    try:
        return [p for p in list(root.glob("*/events.jsonl")) + list(root.glob("*.jsonl")) if p.is_file()]
    except OSError:
        return []


def read_copilot_session(root: str, since: float, cwd: Optional[str] = None) -> dict:
    """Usage of the Copilot CLI session that ended after `since` (a time.time() value), from its `session.shutdown`
    event. Calls run one at a time, so the newest session written since the call started is the call — unless its
    recorded working directory says it belongs to another project. {} when nothing is found."""
    base = Path(os.path.expandvars(os.path.expanduser(root or "")))
    if not root or not base.is_dir():
        return {}
    fresh = []
    for f in _session_files(base):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if mtime >= since - 1:
            fresh.append((mtime, f))
    for _, f in sorted(fresh, reverse=True):
        shutdown, session_cwd = None, None
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            data = ev.get("data") if isinstance(ev.get("data"), dict) else ev
            kind = str(ev.get("type") or "")
            if kind == "session.start":
                ctx = data.get("context") if isinstance(data.get("context"), dict) else data
                session_cwd = ctx.get("cwd") or session_cwd
            elif kind == "session.shutdown":
                shutdown = data
        if shutdown is None:
            continue
        if cwd and session_cwd and not _same_tree(str(session_cwd), str(cwd)):
            continue  # somebody else's session (another project) that happened to end in the same window
        usage = _shutdown_usage(shutdown)
        if usage:
            return usage
    return {}


def _same_tree(a: str, b: str) -> bool:
    """True when one folder is the other or contains it (the CLI may record the repository root for a project that
    lives in a subfolder)."""
    a, b = os.path.realpath(a), os.path.realpath(b)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep) or b.startswith(a.rstrip(os.sep) + os.sep)


# ----------------------------------------------------------------------------- Claude Code
def claude_usage(obj: dict) -> dict:
    """Usage from Claude Code's JSON result object (`total_cost_usd`, `usage`, `duration_api_ms`, `modelUsage`)."""
    out: dict = {}
    if isinstance(obj.get("total_cost_usd"), (int, float)):
        out["cost_usd"] = float(obj["total_cost_usd"])
    u = obj.get("usage")
    if isinstance(u, dict):
        inp = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens"))
        if inp or "input_tokens" in u:
            out["input_tokens"] = inp
        if isinstance(u.get("output_tokens"), (int, float)):
            out["output_tokens"] = int(u["output_tokens"])
        if isinstance(u.get("cache_read_input_tokens"), (int, float)):
            out["cached_tokens"] = int(u["cache_read_input_tokens"])
    if isinstance(obj.get("duration_api_ms"), (int, float)):
        out["api_seconds"] = round(float(obj["duration_api_ms"]) / 1000, 1)
    if isinstance(obj.get("modelUsage"), dict) and obj["modelUsage"]:
        out["model"] = ", ".join(str(k) for k in obj["modelUsage"])
    return out


# ----------------------------------------------------------------------------- ledger
class Ledger:
    """Adds up calls per role. `summary()` is JSON-ready; `merge` combines two summaries (a run and its resume)."""

    def __init__(self):
        self.roles: dict = {}

    def add(self, role: str, seconds: float, usage: Optional[dict] = None) -> None:
        r = self.roles.setdefault(role, {"calls": 0, "seconds": 0.0})
        r["calls"] += 1
        r["seconds"] = round(r["seconds"] + float(seconds), 1)
        for k in NUMERIC:
            v = (usage or {}).get(k)
            if isinstance(v, (int, float)):
                r[k] = round(r.get(k, 0) + v, 4)

    def summary(self) -> dict:
        return summarize(self.roles)

    def total(self, key: str) -> float:
        return float(sum(r.get(key, 0) for r in self.roles.values()))


def summarize(roles: dict) -> dict:
    total: dict = {"calls": 0, "seconds": 0.0}
    for r in roles.values():
        for k, v in r.items():
            if isinstance(v, (int, float)):
                total[k] = round(total.get(k, 0) + v, 4)
    return {"total": total, "by_role": {k: dict(v) for k, v in roles.items()}}


def merge(a: Optional[dict], b: Optional[dict]) -> dict:
    """Two `Ledger.summary()` dicts added together."""
    roles: dict = {}
    for s in (a or {}, b or {}):
        for role, r in (s.get("by_role") or {}).items():
            dst = roles.setdefault(role, {})
            for k, v in r.items():
                if isinstance(v, (int, float)):
                    dst[k] = round(dst.get(k, 0) + v, 4)
    return summarize(roles)


def estimated_cost(summary: dict, premium_request_usd: Optional[float]) -> Optional[float]:
    """Dollars: what the harness reported, plus premium requests × the configured price (None when neither is known)."""
    t = (summary or {}).get("total") or {}
    cost = float(t.get("cost_usd") or 0)
    known = "cost_usd" in t
    if premium_request_usd and t.get("premium_requests"):
        cost += float(t["premium_requests"]) * float(premium_request_usd)
        known = True
    return round(cost, 4) if known else None


def _fmt_tokens(n: float) -> str:
    n = float(n)
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}k"
    return str(int(n))


def describe(r: dict, premium_request_usd: Optional[float] = None) -> str:
    """One line for a role or the total: `12 calls, 34.5 min, 7 premium requests, 453.0k in / 13.1k out, $1.23`."""
    parts = [f"{int(r.get('calls', 0))} call{'s' if r.get('calls', 0) != 1 else ''}", f"{r.get('seconds', 0) / 60:.1f} min"]
    if "premium_requests" in r:
        parts.append(f"{r['premium_requests']:g} premium request{'s' if r['premium_requests'] != 1 else ''}")
    if "input_tokens" in r or "output_tokens" in r:
        tok = f"{_fmt_tokens(r.get('input_tokens', 0))} in / {_fmt_tokens(r.get('output_tokens', 0))} out"
        if r.get("cached_tokens"):
            tok += f" / {_fmt_tokens(r['cached_tokens'])} cached"
        parts.append(tok)
    cost = estimated_cost({"total": r}, premium_request_usd)
    if cost is not None:
        parts.append(f"${cost:.2f}")
    return ", ".join(parts)
