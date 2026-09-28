"""semipilot command line.

    semipilot init                 make this repo ready (config, /refine-requirements and /spec-critic, agents)
    semipilot doctor               check Copilot CLI, git, config and checks
    semipilot preflight <feature>  the evening step: checks + the planner's questions, without starting
    semipilot run <feature>        PilotInLoop: run the loop for approved requirements (asks its questions first)
    semipilot status               where every feature stands
    semipilot review [feature]     print the report, assumptions first
    semipilot resume [feature]     continue an interrupted / blocked run
    semipilot rollback <feature> <task>   git-revert a task and its dependents, set them to pending
    semipilot config               print the effective configuration
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from . import __version__
from .config import Layout, knowledge_layer_present, load_config
from .orchestrator import Loop, NeedsAnswers, PreflightError, Progress, parse_frontmatter, parse_questions


def find_repo(start: Path) -> Path:
    p = Path(start).resolve()
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    raise SystemExit("semipilot: not inside a git repository")


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- commands
def cmd_init(a) -> int:
    from .initcmd import init

    repo = find_repo(a.repo)
    d, report = init(repo, force=a.force)
    say(f"semipilot init → {repo.name} (detected: {d.stack})")
    for action, path in report:
        say(f"  {'installed' if action == 'write' else 'kept     '}  {path.relative_to(repo)}")
    for n in d.notes:
        say(f"  note: {n}")
    say()
    say("Next:")
    say("  1. Open .semipilot/config.yaml and confirm the `checks` commands are right for this repo.")
    say("  2. Fill in .github/copilot-instructions.md (one page: commands, conventions, architecture).")
    say("  3. In VS Code Copilot chat:  /refine-requirements <your idea>   then   /spec-critic   → reply `approve`")
    say("  4. In a terminal:            semipilot run <feature>        (or `semipilot preflight` in the evening, `run` at night)")
    say("Run `semipilot doctor` any time to check the setup.")
    return 0


def cmd_doctor(a) -> int:
    repo = find_repo(a.repo)
    cfg = load_config(repo)
    lay = Layout(repo)
    ok = True

    def check(label: str, good: bool, hint: str = "") -> None:
        nonlocal ok
        ok = ok and good
        say(f"  [{'ok' if good else '!!'}] {label}" + (f" — {hint}" if (hint and not good) else ""))

    say(f"semipilot doctor → {repo.name}")
    check("git repository", True)
    check(".semipilot/config.yaml", lay.config.exists(), "run `semipilot init`")
    check("/refine-requirements and /spec-critic prompts", (repo / ".github/prompts/refine-requirements.prompt.md").exists() and (repo / ".github/prompts/spec-critic.prompt.md").exists(), "run `semipilot init`")
    check("@refiner and @spec-critic agents", (repo / ".github/agents/refiner.agent.md").exists() and (repo / ".github/agents/spec-critic.agent.md").exists(), "run `semipilot init`")
    ref = repo / ".github/agents/refiner.agent.md"
    if ref.exists() and ".semipilot/features" not in ref.read_text(encoding="utf-8"):
        check("@refiner is the semipilot version", False, "an older semiPilotPro refiner is installed; it writes .github/requirements/requirements.md, which `semipilot run` accepts as-is (legacy layout) — or `semipilot init --force` to update it")
    check("PilotInLoop agents", all((repo / f".github/agents/pilotinloop-{n}.agent.md").exists() for n in ("planner", "spec-critic", "plan-critic")), "run `semipilot init`")
    if knowledge_layer_present(repo, cfg):
        vcmd = cfg["knowledge_layer"]["validate_cmd"]
        r = subprocess.run(vcmd, shell=True, cwd=repo, capture_output=True, text=True)
        check(f"knowledge layer healthy (`{vcmd}`)", r.returncode == 0, (r.stdout + r.stderr).strip()[-300:])
    else:
        say("  [--] no knowledge layer (docs/cards + scripts/kb) — optional; agents use copilot-instructions.md and the code")
    instr = repo / ".github/copilot-instructions.md"
    instr_ok = instr.exists() and "<" not in instr.read_text(encoding="utf-8").split("## Conventions")[0]
    check(".github/copilot-instructions.md filled in", instr_ok, "replace the <placeholders> — the critics reject an empty one")
    checks = cfg.get("checks") or []
    todo = [c for c in checks if str(c.get("cmd", "")).lstrip().startswith("#")]
    check(f"checks configured ({len(checks)})", bool(checks) and not todo, "edit `checks` in .semipilot/config.yaml")
    has_task_tests = any("{task_tests}" in str(c.get("cmd", "")) for c in checks)
    check("test check uses {task_tests}", has_task_tests, "without it every task runs the whole suite (slower, still works)")
    cmd = cfg["runner"]["command"].split()[0]
    copilot = shutil.which(cmd)
    check(f"Copilot CLI on PATH ({cmd})", copilot is not None, "install the GitHub Copilot CLI and run `copilot login`")
    if copilot and not a.offline:
        try:
            r = subprocess.run([cmd, "-p", cfg["preflight"]["health_prompt"], "-s", "--no-ask-user"],
                               capture_output=True, text=True, timeout=120, cwd=repo, stdin=subprocess.DEVNULL)
            check("Copilot CLI answers", r.returncode == 0, (r.stdout + r.stderr).strip()[-300:] or "run `copilot login`")
        except Exception as e:  # noqa: BLE001
            check("Copilot CLI answers", False, str(e))
    if not ok:
        say("\nFix the [!!] lines, then run `semipilot doctor` again.")
    else:
        say("\nAll good. Next: /refine-requirements in Copilot chat, then /spec-critic, then `semipilot run <feature>`.")
    return 0 if ok else 1


def feature_state(lay: Layout, slug: str, cfg: dict) -> tuple[str, str]:
    """(stage, hint) for `status`."""
    if lay.report(slug).exists() and lay.progress(slug).exists():
        p = Progress.load(lay.progress(slug))
        done = sum(1 for t in p.tasks if t["status"] == "done")
        return f"ran: {p.stop_reason or 'running'} ({done}/{len(p.tasks)} tasks done)", f"semipilot review {slug}"
    if lay.open_questions(slug).exists():
        n, ans = parse_questions(lay.open_questions(slug).read_text(encoding="utf-8"))
        if n and ans < n:
            return f"waiting for answers ({ans}/{n})", f"answer {lay.rel(lay.open_questions(slug))} then `semipilot run {slug}`"
        if n:
            return "questions answered", f"semipilot run {slug}"
    if lay.requirements(slug).exists():
        fm = parse_frontmatter(lay.requirements(slug).read_text(encoding="utf-8"))
        if str(fm.get("status", "")).lower() == "approved":
            return "requirements approved", f"semipilot preflight {slug}  /  semipilot run {slug}"
        return "requirements drafted, not approved", "/spec-critic in Copilot chat, then `approve`"
    return "empty", "/refine-requirements in Copilot chat"


def cmd_status(a) -> int:
    repo = find_repo(a.repo)
    lay = Layout(repo)
    cfg = load_config(repo)
    feats = lay.list_features()
    if lay.has_legacy_requirements():
        say(f"  (legacy) {Layout.LEGACY_DIR}/requirements.md found — `semipilot run <any-slug>` uses it when no per-feature folder exists")
    if not feats:
        say("no features yet — start with `/refine-requirements <idea>` in Copilot chat")
        return 0
    say(f"features in {repo.name}:")
    for slug in feats:
        stage, hint = feature_state(lay, slug, cfg)
        say(f"  {slug:<32} {stage:<45} → {hint}")
    return 0


def resolve_feature(lay: Layout, given: str | None) -> str:
    if given:
        return given
    if lay.last_run.exists():
        return lay.last_run.read_text(encoding="utf-8").strip()
    feats = lay.list_features()
    if len(feats) == 1:
        return feats[0]
    raise SystemExit("semipilot: which feature? pass its slug (see `semipilot status`)")


def cmd_run(a) -> int:
    repo = find_repo(a.repo)
    cfg = load_config(repo)
    loop = Loop(repo, cfg, a.feature)
    preflight_only = getattr(a, "preflight_only", False)
    try:
        reason = loop.run(skip_questions=a.no_questions, preflight_only=preflight_only)
    except NeedsAnswers as q:
        say()
        say(f"The planner has {q.count} question(s) before it can start:")
        say(f"  {Layout(repo).rel(q.path)}")
        say()
        say("Fill in each `Answer:` line (accept the recommended default by copying it), save, then run:")
        say(f"  semipilot run {a.feature}")
        say("Five minutes here is the best-leveraged time of the whole run.")
        return 3
    except PreflightError as e:
        say(f"\nCannot start: {e}", )
        return 1
    say()
    if reason == "preflight_ok":
        say(f"Ready. Start the run when the machine can stay awake:\n  semipilot run {a.feature}")
        return 0
    say(f"stop reason: {reason}")
    say(f"report: {Layout(repo).rel(loop.report_path)}")
    say(f"next:   semipilot review {a.feature}")
    return 0 if reason == "completed" else 2


def cmd_resume(a) -> int:
    repo = find_repo(a.repo)
    cfg = load_config(repo)
    slug = resolve_feature(Layout(repo), a.feature)
    loop = Loop(repo, cfg, slug)
    try:
        reason = loop.resume()
    except PreflightError as e:
        say(f"\nCannot resume: {e}")
        return 1
    say(f"\nstop reason: {reason}\nnext: semipilot review {slug}")
    return 0 if reason == "completed" else 2


def cmd_rollback(a) -> int:
    repo = find_repo(a.repo)
    cfg = load_config(repo)
    loop = Loop(repo, cfg, a.feature)
    try:
        loop.rollback(a.task)
    except PreflightError as e:
        say(f"\nCannot rollback: {e}")
        return 1
    say(f"\n{a.task} and its dependents are reverted and pending. Fix the spec or decisions, then `semipilot resume {a.feature}`.")
    return 0


def cmd_review(a) -> int:
    repo = find_repo(a.repo)
    lay = Layout(repo)
    slug = resolve_feature(lay, a.feature)
    rep = lay.report(slug)
    if not rep.exists():
        say(f"no report for '{slug}' yet (run `semipilot run {slug}`)")
        return 1
    say(rep.read_text(encoding="utf-8"))
    return 0


def cmd_config(a) -> int:
    repo = find_repo(a.repo)
    cfg = load_config(repo)
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
    say(yaml.safe_dump(cfg, sort_keys=False))
    return 0


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="semipilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"semipilot {__version__}")
    ap.add_argument("--repo", default=".", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="make this repo ready: config, /refine-requirements and /spec-critic prompts, agents")
    p.add_argument("--force", action="store_true", help="overwrite semipilot's own files (never your instructions)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("doctor", help="check Copilot CLI, config and checks")
    p.add_argument("--offline", action="store_true", help="skip the Copilot CLI call")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("preflight", help="evening step: checks + the planner's questions, without starting the run")
    p.add_argument("feature")
    p.add_argument("--no-questions", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run, preflight_only=True)

    p = sub.add_parser("run", aliases=["pilotinloop"], help="PilotInLoop: run the loop for approved requirements")
    p.add_argument("feature")
    p.add_argument("--no-questions", action="store_true", help="skip the planner's questions (assumptions get logged instead)")
    p.set_defaults(fn=cmd_run, preflight_only=False)

    p = sub.add_parser("status", help="where every feature stands")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("review", help="print a feature's report")
    p.add_argument("feature", nargs="?")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("resume", help="continue an interrupted or blocked run")
    p.add_argument("feature", nargs="?")
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("rollback", help="revert a task and its dependents")
    p.add_argument("feature")
    p.add_argument("task", help="task id, e.g. T3")
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("config", help="print the effective configuration")
    p.set_defaults(fn=cmd_config)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
