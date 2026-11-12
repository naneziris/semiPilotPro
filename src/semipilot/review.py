"""The review gate, made cheaper for the human.

The one expensive step of a run is a person reading what the loop built. Two things here spend machine time to
save that person's time:

- `run_reviewer(loop)` — one read-only agent call after the last task. It reads the whole diff and grades it against
  a rubric (`roles/reviewer.md`, override with `.semipilot/roles/reviewer.md`), listing findings and the places a
  human should open first. It never blocks a run and never edits anything: it is advice to the reviewer.
- `packet(loop)` — the top of report.md: verdict and risk tier, what to read first, the evidence per acceptance
  criterion (criterion → test → task → commit, and whether the test was red before the code existed), where the
  change is, and a reading order commit by commit. Built from facts the orchestrator recorded; the reviewer agent's
  output is one input among several.
"""
from __future__ import annotations

import re
from typing import Optional

from .runner import HaltRun, Runner

VERDICTS = ("ship", "ship_with_notes", "needs_changes")
SEVERITIES = ("blocker", "major", "minor")
SCORES = ("pass", "concern", "fail")
VERDICT_WORDS = {"ship": "ship", "ship_with_notes": "ship, with notes", "needs_changes": "needs changes"}


def review_cfg(cfg: dict) -> dict:
    r = cfg.get("review")
    return r if isinstance(r, dict) else {}


def _one_line(text, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def normalize(raw: Optional[dict], max_findings: int) -> dict:
    """The reviewer's JSON, with every field forced into the shape the report expects."""
    raw = raw if isinstance(raw, dict) else {}
    verdict = str(raw.get("verdict") or "").strip().lower()
    out = {"verdict": verdict if verdict in VERDICTS else "no_verdict", "summary": _one_line(raw.get("summary"), 600),
           "rubric": [], "findings": [], "read_first": []}
    for item in raw.get("rubric") or []:
        if isinstance(item, dict) and item.get("id"):
            score = str(item.get("score") or "").strip().lower()
            out["rubric"].append({"id": _one_line(item["id"], 40), "score": score if score in SCORES else "concern",
                                  "evidence": _one_line(item.get("evidence"))})
    for f in raw.get("findings") or []:
        if not isinstance(f, dict) or not f.get("note"):
            continue
        sev = str(f.get("severity") or "").strip().lower()
        line = f.get("line")
        out["findings"].append({"severity": sev if sev in SEVERITIES else "minor", "file": _one_line(f.get("file"), 200),
                                "line": line if isinstance(line, int) else None,
                                "task": _one_line(f.get("task"), 10) or None, "note": _one_line(f["note"], 500),
                                "suggestion": _one_line(f.get("suggestion"), 500)})
    out["findings"].sort(key=lambda f: SEVERITIES.index(f["severity"]))
    out["findings"] = out["findings"][:max_findings]
    out["read_first"] = [_one_line(x) for x in (raw.get("read_first") or []) if _one_line(x)][:8]
    if out["verdict"] != "needs_changes" and (any(f["severity"] == "blocker" for f in out["findings"])
                                              or any(r["score"] == "fail" for r in out["rubric"])):
        out["verdict"] = "needs_changes"  # a blocker or a failed rubric item is never "ship", whatever the label says
    return out


def signals(loop) -> list[str]:
    """What the orchestrator knows that tells a reviewer (agent or human) where to look."""
    p = loop.progress
    out = []
    if p.final_checks_passed is False:
        out.append("the final full-suite checks FAILED although every task passed its own checks")
    for t in p.tasks:
        if t["status"] == "blocked":
            out.append(f"{t['id']} is blocked: {t.get('blocked_reason')}")
        elif t.get("attempts", 0) > 1:
            out.append(f"{t['id']} needed {t['attempts']} attempts")
    out += [w for w in p.warnings if any(k in w for k in ("REVIEW", "outside scope", "scope violation", "no locked test",
                                                           "modified locked tests", "changed local file"))]
    risk = p.risk or {}
    if risk.get("escalated_by"):
        out.append(f"risk raised to {risk.get('effective')} because the plan touches: {', '.join(risk['escalated_by'])}")
    return out


def run_reviewer(loop) -> None:
    """One read-only reviewer call over the finished branch; the result goes into the checkpoint (`review`).
    A reviewer that cannot run (quota, outage, no JSON) is a note in the report, never a failed run."""
    cfg = review_cfg(loop.cfg)
    p = loop.progress
    done = [t for t in p.tasks if t["status"] == "done" and t.get("commit")]
    if not cfg.get("agent", True) or not done:
        return
    head = loop.last_good_commit()  # the last task's commit: what was built (later commits only hold run state)
    if (p.review or {}).get("head") == head and (p.review or {}).get("verdict") in VERDICTS:
        return  # this exact commit was already reviewed (a resume that changed nothing)
    by_id = {t["id"]: t for t in (loop.plan or {}).get("tasks", [])}
    tasks = "\n".join(f"- {t['id']} {t['title']} — commit {t['commit'][:10]} — files: "
                      f"{', '.join(by_id.get(t['id'], {}).get('expected_files', []))}" for t in done)
    sig = signals(loop)
    max_findings = int(cfg.get("max_findings", 20))
    prompt = loop.prompt("reviewer", feature=loop.feature, risk=(p.risk or {}).get("effective", "low"),
                         spec_path=loop.spec_rel, questions_path=loop.questions_rel, decisions_path=loop.decisions_rel,
                         plan_path=loop.lay.rel(loop.lay.implementation_plan(loop.feature)), base=p.base_commit[:12],
                         head=head[:12], state_path=loop.lay.rel(loop.lay.root), tasks=tasks,
                         signals="\n".join(f"- {s}" for s in sig) or "- nothing unusual", max_findings=str(max_findings),
                         **{k: v for k, v in loop.kl_context().items() if k == "knowledge"})
    snap = loop.local_snapshot()
    try:
        res = loop.runner.run("reviewer", prompt, "reviewer")
    except HaltRun as h:
        p.review = {"verdict": "not_run", "head": head, "summary": f"the reviewer could not run ({h.reason})"}
        p.warnings.append(f"reviewer did not run: {h.reason} — `semipilot review {loop.feature} --agent` runs it again")
        loop.log(f"reviewer did not run: {h.reason}")
        return
    loop.restore_local(snap, "the reviewer")
    try:
        loop.guard_branch("the reviewer")
    except HaltRun as h:
        p.warnings.append(f"reviewer: {h.detail}")
    if loop.code_dirty():  # read-only by its permission profile; undo anything it changed regardless
        loop.reset_tree("reviewer changed files")
    verdict = normalize(Runner.extract_json(res.text), max_findings)
    verdict["head"] = head
    if verdict["verdict"] == "no_verdict":
        verdict["summary"] = verdict["summary"] or "the reviewer returned no JSON verdict (see its call log)"
    p.review = verdict
    blockers = sum(1 for f in verdict["findings"] if f["severity"] == "blocker")
    loop.log(f"reviewer: {VERDICT_WORDS.get(verdict['verdict'], verdict['verdict'])} — {len(verdict['findings'])} "
             f"finding(s), {blockers} blocker(s)")


# ----------------------------------------------------------------------------- the packet
def criterion_evidence(loop) -> list[dict]:
    """Per acceptance criterion: the locked test files naming its ref, the task that owns it, that task's status and
    commit, and whether the tests were red before the implementation."""
    p = loop.progress
    plan_tasks = (loop.plan or {}).get("tasks", [])
    check_names = {str(c.get("name")) for c in loop.cfg.get("checks") or []}
    out = []
    for c in loop.criteria():
        ref = c["ref"]
        files = []
        for f in sorted(loop.lock.checksums):
            fp = loop.repo / f
            try:
                if fp.exists() and ref in fp.read_text(encoding="utf-8", errors="ignore"):
                    files.append(f)
            except OSError:
                pass
        owners = [t["id"] for t in plan_tasks if ref in t.get("acceptance_checks", [])]
        entry = next((e for e in p.tasks if e["id"] in owners), None)
        out.append({"ref": ref, "text": c["text"], "tests": files, "is_check": ref in check_names, "task": owners,
                    "status": entry["status"] if entry else "not planned", "commit": (entry or {}).get("commit"),
                    "red": [(p.red_check or {}).get(o) for o in owners]})
    return out


def change_map(loop, limit: int = 12) -> tuple[list[dict], int]:
    """Files changed by the run, biggest first, each with the task that planned it (None = nobody planned it)."""
    p = loop.progress
    head = loop.last_good_commit()
    if not p.base_commit or head == p.base_commit:
        return [], 0
    planned = {}
    for t in (loop.plan or {}).get("tasks", []):
        for f in t.get("expected_files", []):
            planned.setdefault(f, t["id"])
    rows = []
    for line in loop.git.run("diff", "--numstat", "--relative", p.base_commit, head, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or loop.is_managed(parts[2]) or loop.git.is_local(parts[2]):
            continue
        add = int(parts[0]) if parts[0].isdigit() else 0
        rem = int(parts[1]) if parts[1].isdigit() else 0
        rows.append({"file": parts[2], "added": add, "removed": rem, "task": planned.get(parts[2]),
                     "test": loop.lock.matches(parts[2])})
    rows.sort(key=lambda r: -(r["added"] + r["removed"]))
    return rows[:limit], len(rows)


def attention(loop) -> list[str]:
    """Reasons this run needs more than a routine read (empty = none found)."""
    p = loop.progress
    why = []
    rv = p.review or {}
    blockers = [f for f in rv.get("findings", []) if f["severity"] == "blocker"]
    if blockers:
        why.append(f"{len(blockers)} blocker(s) from the reviewer")
    elif rv.get("verdict") == "needs_changes":
        why.append("the reviewer's verdict is needs changes")
    if p.final_checks_passed is False:
        why.append("the final full-suite checks failed")
    blocked = [t["id"] for t in p.tasks if t["status"] == "blocked"]
    if blocked:
        why.append(f"blocked: {', '.join(blocked)}")
    green = [tid for tid, s in (p.red_check or {}).items() if s == "green"]
    if green:
        why.append(f"tests of {', '.join(green)} passed before the code existed")
    return why


def packet(loop) -> list[str]:
    """Report lines for `## 0. Review packet`."""
    p = loop.progress
    rv = p.review or {}
    risk = p.risk or {}
    L = ["## 0. Review packet", ""]
    tier = risk.get("effective")
    if tier:
        declared = risk.get("declared")
        note = "" if declared == tier else (f" (requirements say {declared})" if declared else " (default — the requirements name none)")
        if risk.get("escalated_by"):
            note = f" (raised from {declared or 'the default'}: the plan touches {', '.join(risk['escalated_by'][:4])})"
        L.append(f"- Risk tier: **{tier}**{note}")
        approval = p.plan_approval or {}
        if approval.get("at"):
            L.append(f"- Plan approved by a human at {approval['at'][:16].replace('T', ' ')}")
    if rv:
        words = VERDICT_WORDS.get(rv.get("verdict"), {"not_run": "did not run", "no_verdict": "no verdict"}.get(rv.get("verdict"), "—"))
        L.append(f"- Reviewer agent: **{words}**" + (f" — {rv['summary']}" if rv.get("summary") else ""))
    why = attention(loop)
    L.append(f"- Needs attention: {'; '.join(why)}" if why else "- Nothing mechanical stands out; the review is still yours.")

    first = []
    dec = loop.decisions_text()
    n_dec = len(re.findall(r"^## D-", dec, re.MULTILINE))
    if n_dec:
        first.append(f"{n_dec} assumption(s) the loop made — section 1 below; a wrong one is the cheapest thing to catch now")
    for f in rv.get("findings", []):
        if f["severity"] in ("blocker", "major"):
            where = f["file"] + (f":{f['line']}" if f.get("line") else "")
            first.append(f"**{f['severity']}** {where} — {f['note']}")
    first += rv.get("read_first", [])
    first += [s for s in signals(loop) if not s.startswith("risk raised")]
    L += ["", "### Read first", ""]
    L += [f"{i}. {x}" for i, x in enumerate(dict.fromkeys(first), 1)] or ["_Nothing flagged._"]

    ev = criterion_evidence(loop)
    L += ["", "### Evidence per acceptance criterion", "",
          "| Criterion | Check | Test file | Task | Status | Red first |", "|---|---|---|---|---|---|"]
    for e in ev:
        if e["tests"]:
            tests = ", ".join(f"`{t}`" for t in e["tests"])
        else:
            tests = "(a configured check)" if e["is_check"] else "**none found**"
        red = {"red": "yes", "green": "**no**", None: "—"}.get(next((r for r in e["red"] if r), None), "—")
        commit = f" `{e['commit'][:8]}`" if e.get("commit") else ""
        L.append(f"| {_one_line(e['text'], 90).replace('|', '/')} | `{e['ref']}` | {tests} | {', '.join(e['task']) or '—'}"
                 f" | {e['status']}{commit} | {red} |")
    if not ev:
        L.append("| _no tagged criteria_ | | | | | |")

    rows, total = change_map(loop)
    L += ["", "### Where the change is", ""]
    if rows:
        L += ["| File | +/- | Planned by |", "|---|---|---|"]
        for r in rows:
            owner = r["task"] or ("locked test" if r["file"] in loop.lock.checksums else
                                  "new test" if r["test"] else "**not in the plan**")
            L.append(f"| `{r['file']}` | +{r['added']}/-{r['removed']} | {owner} |")
        if total > len(rows):
            L.append(f"| … {total - len(rows)} more file(s) | | |")
    else:
        L.append("_No code committed._")

    done = [t for t in p.tasks if t["status"] == "done" and t.get("commit")]
    if done:
        L += ["", "### Reading order", "",
              "One task per commit, in dependency order — read a commit, then its test:", ""]
        L += [f"- `git show {t['commit'][:8]}` — {t['id']} {t['title']}"
              + (f" ({t['diff']['files']} file{'s' if t['diff']['files'] != 1 else ''}, +{t['diff']['added']}/-{t['diff']['removed']})" if t.get("diff") else "")
              for t in done]

    if rv.get("rubric") or rv.get("findings"):
        L += ["", "### Reviewer agent — rubric", ""]
        if rv.get("rubric"):
            L += ["| Item | Score | Evidence |", "|---|---|---|"]
            L += [f"| {r['id']} | {'**' + r['score'] + '**' if r['score'] != 'pass' else 'pass'} | {r['evidence'].replace('|', '/')} |"
                  for r in rv["rubric"]]
        if rv.get("findings"):
            L += ["", "Findings:", ""]
            for f in rv["findings"]:
                where = f["file"] + (f":{f['line']}" if f.get("line") else "")
                task = f" ({f['task']})" if f.get("task") else ""
                L.append(f"- **{f['severity']}** `{where}`{task} — {f['note']}" + (f" → {f['suggestion']}" if f.get("suggestion") else ""))
        L += ["", "_The reviewer is an agent grading against a rubric: it points, it does not decide. Verify what it says in the code._"]
    L.append("")
    return L


def mr_body(loop, issue: Optional[str] = None) -> str:
    """The merge request description: what was built, what a reviewer should know, how it was verified."""
    p = loop.progress
    rv = p.review or {}
    fm_title = re.search(r"^#\s+(?:Requirement:\s*)?(.+)$", loop.spec_text(), re.MULTILINE)
    L = [f"## {fm_title.group(1).strip() if fm_title else p.feature}", ""]
    done = [t for t in p.tasks if t["status"] == "done"]
    L += [f"- {t['title']}" for t in done] or ["- (no completed tasks)"]
    left = [t for t in p.tasks if t["status"] != "done"]
    if left:
        L += ["", "Not included:"] + [f"- {t['title']} ({t['status']})" for t in left]
    L += ["", "### For the reviewer", ""]
    risk = p.risk or {}
    if risk.get("effective"):
        L.append(f"- Risk tier: {risk['effective']}"
                 + (" — the plan was approved by a person before anything was built" if (p.plan_approval or {}).get("at") else ""))
    if rv.get("verdict") in VERDICTS:
        L.append(f"- Automated review: {VERDICT_WORDS[rv['verdict']]}" + (f" — {rv['summary']}" if rv.get("summary") else ""))
    n_dec = len(re.findall(r"^## D-", loop.decisions_text(), re.MULTILINE))
    if n_dec:
        L.append(f"- {n_dec} assumption(s) were made where the requirements were silent — please confirm them")
    for f in rv.get("findings", []):
        if f["severity"] in ("blocker", "major"):
            L.append(f"- {f['severity']}: `{f['file']}` — {f['note']}")
    for x in rv.get("read_first", [])[:5]:
        L.append(f"- Read first: {x}")
    L += ["", "### Verification", ""]
    for e in criterion_evidence(loop):
        L.append(f"- [{'x' if e['status'] == 'done' else ' '}] {_one_line(e['text'], 160)} — `{e['ref']}`")
    if p.check_results:
        L.append("")
        L.append("Checks: " + ", ".join(f"{c['name']} {'pass' if c['passed'] else 'FAIL'}" for c in p.check_results)
                 + (" (full suite)" if p.final_checks_passed is not None else ""))
    if issue:
        L += ["", f"Closes {issue}"]
    return "\n".join(L).strip() + "\n"
