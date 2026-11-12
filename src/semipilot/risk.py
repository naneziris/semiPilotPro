"""How much of a run a feature may do without a human: its risk tier.

One switch per feature instead of one for everything. The tier comes from `risk:` in the requirements' frontmatter
(written by semipilot-refine, checked at Gate 1) and can only be raised, never lowered, by the paths the accepted
plan touches (`autonomy.escalate`): a "low" feature that turns out to edit the auth module is not low.

    low      the checks are the gate: plan, tests, implementation and report run unattended (the v0.2 behaviour)
    medium   + the run stops once after the critics accept the plan; a human reads implementation-plan.md and
               runs `semipilot approve` (or `semipilot replan -m "<what to change>"`)
    high     + the run stops after every task; a human reads that commit and runs `semipilot resume`
               (or `semipilot rollback`)

What each tier adds is configuration (`autonomy.tiers`), so a team can, for instance, review every task at medium.
"""
from __future__ import annotations

import fnmatch
from typing import Optional

TIERS = ("low", "medium", "high")
GATES = ("plan_approval", "task_review")
DEFAULT_GATES = {
    "low": {"plan_approval": False, "task_review": False},
    "medium": {"plan_approval": True, "task_review": False},
    "high": {"plan_approval": True, "task_review": True},
}


class RiskError(ValueError):
    pass


def rank(tier: str) -> int:
    return TIERS.index(tier)


def highest(*tiers: Optional[str]) -> str:
    return max((t for t in tiers if t), key=rank, default="low")


def declared_risk(frontmatter: dict) -> Optional[str]:
    """`risk:` from the requirements' frontmatter, validated; None when absent."""
    raw = str(frontmatter.get("risk") or "").strip().lower()
    if not raw:
        return None
    if raw not in TIERS:
        raise RiskError(f"risk: {raw!r} is not one of {', '.join(TIERS)}")
    return raw


def default_risk(cfg: dict) -> str:
    raw = str((cfg.get("autonomy") or {}).get("default_risk") or "low").strip().lower()
    if raw not in TIERS:
        raise RiskError(f"autonomy.default_risk: {raw!r} is not one of {', '.join(TIERS)}")
    return raw


def path_matches(path: str, pattern: str) -> bool:
    """Glob match on a project-relative path. `**/auth/**` also matches a top-level `auth/x.py`, and a pattern
    ending in `/` means everything under that folder."""
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    pat = pattern.replace("\\", "/")
    if pat.endswith("/"):
        pat += "**"
    candidates = {pat}
    while pat.startswith("**/"):
        pat = pat[3:]
        candidates.add(pat)
    return any(fnmatch.fnmatchcase(path, c) for c in candidates)


def escalation(files: list[str], cfg: dict) -> tuple[Optional[str], list[str]]:
    """(the tier the touched paths demand, the files that demand it) — (None, []) when no pattern matches."""
    esc = (cfg.get("autonomy") or {}).get("escalate") or {}
    for tier in reversed(TIERS):
        patterns = [p for p in (esc.get(tier) or []) if p]
        hits = sorted({f for f in files if any(path_matches(f, p) for p in patterns)})
        if hits:
            return tier, hits
    return None, []


def gates(cfg: dict, tier: str) -> dict:
    """The human gates a tier adds: {"plan_approval": bool, "task_review": bool}."""
    configured = ((cfg.get("autonomy") or {}).get("tiers") or {}).get(tier) or {}
    out = dict(DEFAULT_GATES[tier])
    for g in GATES:
        if g in configured:
            out[g] = bool(configured[g])
    return out


def assess(frontmatter: dict, cfg: dict, planned_files: Optional[list[str]] = None) -> dict:
    """The feature's risk as a record for the checkpoint and the report:
    {"declared": tier|None, "effective": tier, "escalated_by": [files], "gates": {...}}."""
    declared = declared_risk(frontmatter)
    base = declared or default_risk(cfg)
    esc_tier, hits = escalation(planned_files or [], cfg)
    effective = highest(base, esc_tier)
    return {"declared": declared, "effective": effective,
            "escalated_by": hits if esc_tier and rank(esc_tier) > rank(base) else [],
            "gates": gates(cfg, effective)}
