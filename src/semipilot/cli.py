"""semipilot command line.

    semipilot init                 make this project ready: config, the skill pack for your agent, AGENTS.md
    semipilot doctor               check the harness CLI, git, config, skills, instructions and checks
    semipilot preflight <feature>  checks + the planner's questions, without starting the run
    semipilot run <feature>        PilotInLoop: run the loop for approved requirements on a new branch made from
                                   the branch you are on (asks its questions first)
    semipilot status               where every feature stands
    semipilot review [feature]     print the report, assumptions first
    semipilot resume [feature]     continue an interrupted / blocked run
    semipilot rollback <feature> <task>   git-revert a task and its dependents, set them to pending
    semipilot kb init|validate|index|resolve|drift|guard|catchup   the knowledge layer
    semipilot config               print the effective configuration
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ._yaml import yaml

from . import __version__
from .config import (CONFIG_FILE, SEMIPILOT_DIR, Layout, instructions_file, kb_commands, kb_flavor,
                     knowledge_layer_present, legacy_config_notes, load_config)
from .harness import UnknownHarnessError, get_harness
from .orchestrator import Git, Loop, NeedsAnswers, PreflightError, Progress, parse_frontmatter, parse_questions
from .runner import HaltRun
from .skills_pack import SKILL_DIRS, SKILLS


def find_repo(start: Path) -> Path:
    """The project root: the nearest ancestor with `.semipilot/config.yaml` (a project set up with
    `semipilot init --here` inside a bigger repository), else the git root."""
    p = Path(start).resolve()
    for cand in (p, *p.parents):
        if (cand / SEMIPILOT_DIR / CONFIG_FILE).exists():
            return cand
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    raise SystemExit("semipilot: not inside a git repository")


def git_root(start: Path) -> Path:
    p = Path(start).resolve()
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    raise SystemExit("semipilot: not inside a git repository")


def say(msg: str = "") -> None:
    print(msg, flush=True)


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(path, base)


def _filled(text: str) -> bool:
    """An instructions file still holding template placeholders counts as empty."""
    if "{{TODO" in text:
        return False
    return not re.search(r"^\s*-\s*<[^>\n]+>\s*$", text, re.MULTILINE)


# --------------------------------------------------------------------------- commands
def cmd_init(a) -> int:
    from .initcmd import init

    repo = Path(a.repo).resolve() if a.here else find_repo(a.repo)
    if a.here:
        git_root(repo)  # exits when not inside a git repository
    skills_for = None
    if a.skills:
        skills_for = ["copilot", "claude"] if a.skills.strip().lower() in ("both", "all") else \
            [x for x in re.split(r"[,\s]+", a.skills) if x]
    d, report, info = init(repo, force=a.force, harness=a.harness, skills_for=skills_for)
    h = info["harness"]
    say(f"semipilot init → {repo.name} (detected: {d.stack}; loop harness: {h}, {info['why']})")
    for action, path in report:
        label = {"write": "installed", "update": "updated  "}.get(action, "kept     ")
        say(f"  {label}  {_rel(path, repo)}")
    for n in info["notes"]:
        say(f"  note: {n}")
    chat = " / ".join({"copilot": "VS Code Copilot chat or Copilot CLI", "claude": "Claude Code"}[c] for c in info["skills_for"])
    say()
    say("Next:")
    say("  1. Open .semipilot/config.yaml and confirm the `checks` commands are right for this project.")
    say(f"  2. Fill in {info['instructions']} (one page: commands, conventions, architecture) — every agent reads it.")
    say(f"  3. In {chat}:  /semipilot-refine <your idea>   then   /semipilot-spec-critic   → reply `approve`")
    say("  4. In a terminal, on your base branch (usually main):  semipilot run <feature>   — it creates feat/<feature> from there")
    say("                               (`semipilot preflight <feature>` first does the checks and the planner's questions only)")
    say("Optional: `semipilot kb init` adds the knowledge layer (module cards + deterministic retrieval).")
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

    def info(label: str) -> None:
        say(f"  [--] {label}")

    say(f"semipilot doctor → {repo.name}")
    prefix = Git(repo).prefix
    if prefix:
        check(f"project {prefix} inside repository {git_root(repo).name} (.semipilot, skills and the knowledge layer are looked up here)", True)
    else:
        check("git repository (project = repository root)", True)
    check(".semipilot/config.yaml", lay.config.exists(), "run `semipilot init`")
    try:
        harness = get_harness(cfg)
        check(f"harness: {harness.name} ({harness.label})", True)
    except UnknownHarnessError as e:
        check("harness", False, str(e))
        harness = None
    for n in legacy_config_notes(cfg):
        info(n)
    installed = [h for h, d in SKILL_DIRS.items() if all((repo / d / s / "SKILL.md").exists() for s in SKILLS)]
    if harness:
        check(f"skill pack in {SKILL_DIRS[harness.name]}/ (semipilot-refine, -spec-critic, -run, -scribe, -knowledge)",
              harness.name in installed, f"run `semipilot init --harness {harness.name}` (or --skills both)")
    for h in installed:
        if not harness or h != harness.name:
            info(f"skill pack also installed for {h} ({SKILL_DIRS[h]}/)")
    for legacy in (".github/agents/pilotinloop-planner.agent.md", ".github/prompts/refine-requirements.prompt.md"):
        if (repo / legacy).exists():
            info(f"{legacy} is from v0.1 and no longer used (skills and inlined roles replace it); delete when ready")
    if knowledge_layer_present(repo, cfg):
        vcmd, _ = kb_commands(repo, cfg)
        r = subprocess.run(vcmd, shell=True, cwd=repo, capture_output=True, text=True)
        check(f"knowledge layer healthy (`{vcmd}`)", r.returncode == 0, (r.stdout + r.stderr).strip()[-300:])
        if kb_flavor(repo) == "node":
            info("knowledge layer uses the Node scripts — `semipilot kb init --force` switches to scripts/kb/kb.py (cards untouched)")
    else:
        info("no knowledge layer (docs/cards + scripts/kb) — optional; `semipilot kb init` adds it")
    main = instructions_file(repo, cfg)
    p = repo / main
    check(f"{main} filled in", p.exists() and _filled(p.read_text(encoding="utf-8")),
          "replace the {{TODO}} / <placeholder> lines — the critics reject an empty one")
    if harness and harness.name == "claude" and main == ".github/copilot-instructions.md" and not (repo / "CLAUDE.md").exists():
        check("Claude Code can read the instructions", False, "add CLAUDE.md with the line `@.github/copilot-instructions.md`, or move them to AGENTS.md")
    if harness and harness.name == "claude" and (repo / "CLAUDE.md").exists() and (repo / "AGENTS.md").exists() \
            and "AGENTS.md" not in (repo / "CLAUDE.md").read_text(encoding="utf-8"):
        check("Claude Code can read AGENTS.md", False, "CLAUDE.md exists, so Claude Code skips AGENTS.md — add a line `@AGENTS.md` to CLAUDE.md")
    checks = cfg.get("checks") or []
    todo = [c for c in checks if str(c.get("cmd", "")).lstrip().startswith("#")]
    check(f"checks configured ({len(checks)})", bool(checks) and not todo, "edit `checks` in .semipilot/config.yaml")
    has_task_tests = any("{task_tests}" in str(c.get("cmd", "")) for c in checks)
    check("test check uses {task_tests}", has_task_tests, "without it every task runs the whole suite (slower, still works)")
    if harness:
        exe = harness.executable[0]
        found = shutil.which(exe) is not None
        check(f"{harness.label} on PATH ({exe})", found, harness.install_hint)
        if found and not a.offline:
            try:
                inv = harness.health(cfg["preflight"]["health_prompt"], str(lay.runs / "doctor"))
                kw = {"input": inv.stdin} if inv.stdin is not None else {"stdin": subprocess.DEVNULL}
                r = subprocess.run(inv.argv, capture_output=True, text=True, timeout=180, cwd=repo, **kw)
                text, meta = harness.response(r.stdout)
                good = r.returncode == 0 and not meta.get("is_error")
                check(f"{harness.label} answers", good, (text + r.stderr).strip()[-300:] or f"log in: {harness.login_hint}")
            except Exception as e:  # noqa: BLE001
                check(f"{harness.label} answers", False, str(e))
    if not ok:
        say("\nFix the [!!] lines, then run `semipilot doctor` again.")
    else:
        say("\nAll good. Next: /semipilot-refine in your agent's chat, then /semipilot-spec-critic, then `semipilot run <feature>`.")
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
        return "requirements drafted, not approved", "/semipilot-spec-critic in your agent's chat, then `approve`"
    return "empty", "/semipilot-refine in your agent's chat"


def cmd_status(a) -> int:
    repo = find_repo(a.repo)
    lay = Layout(repo)
    cfg = load_config(repo)
    feats = lay.list_features()
    if lay.has_legacy_requirements():
        say(f"  (legacy) {Layout.LEGACY_DIR}/requirements.md found — `semipilot run <any-slug>` uses it when no per-feature folder exists")
    if not feats:
        say("no features yet — start with `/semipilot-refine <idea>` in your agent's chat")
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
    if getattr(a, "branch", None):
        cfg["git"]["branch"] = a.branch
    loop = Loop(repo, cfg, a.feature)
    preflight_only = getattr(a, "preflight_only", False)
    try:
        reason = loop.run(skip_questions=a.no_questions, preflight_only=preflight_only, stack=getattr(a, "stack", False))
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
    except HaltRun as h:  # e.g. auth or quota failure during the planner's questions, before the run starts
        say(f"\nStopped before the run started: {h.reason} — {h.detail}")
        return 2
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


def cmd_kb(a) -> int:
    from .kbcmd import kb_init, run_kb

    args = list(a.kb_args or [])
    if not args or args[0] in ("-h", "--help"):
        say(__doc__.split("semipilot config")[0].strip().splitlines()[0])
        say("usage: semipilot kb init [--system <prefix>] [--force]")
        say("       semipilot kb validate | index [--check] | resolve --tags a,b [--json] | drift [--verbose] | guard [--files ...] | catchup [--mark]")
        return 0 if args else 2
    if args[0] == "--help-tool":
        return run_kb(find_repo(a.repo), ["--help"])
    if args[0] == "init":
        ip = argparse.ArgumentParser(prog="semipilot kb init")
        ip.add_argument("--system", default="", help="lowercase-kebab prefix for card ids (default: the project folder name)")
        ip.add_argument("--force", action="store_true", help="refresh kb.py, the hook and the CI workflow (never knowledge content)")
        ia = ip.parse_args(args[1:])
        repo = find_repo(a.repo)
        report, notes = kb_init(repo, ia.system, ia.force)
        say(f"semipilot kb init → {repo.name}")
        for action, path in report:
            label = {"write": "installed", "update": "updated  "}.get(action, "kept     ")
            say(f"  {label}  {_rel(path, repo)}")
        for n in notes:
            say(f"  note: {n}")
        say()
        say("Next: fill the layer with your agent — `/semipilot-knowledge bootstrap` — and approve each gate.")
        say("Then `semipilot kb validate && semipilot kb index` and commit.")
        return 0
    return run_kb(find_repo(a.repo), args)


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

    p = sub.add_parser("init", help="make this project ready: config, the skill pack for your agent, AGENTS.md")
    p.add_argument("--harness", help="the agent CLI that runs the loop: copilot | claude (default: existing config, else the one on PATH, else copilot)")
    p.add_argument("--skills", help="install the skill pack for these chats: copilot, claude or both (default: the harness)")
    p.add_argument("--force", action="store_true", help="reinstall the semipilot-* skill folders even when they are current (your config and instructions are never overwritten)")
    p.add_argument("--here", action="store_true", help="set up the current directory as the project (for a project that lives in a subfolder of a bigger repository); later commands find it from anywhere inside")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("doctor", help="check the harness CLI, config, skills, instructions and checks")
    p.add_argument("--offline", action="store_true", help="skip the call to the agent CLI")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("preflight", help="checks + the planner's questions, without starting the run")
    p.add_argument("feature")
    p.add_argument("--no-questions", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run, preflight_only=True)

    p = sub.add_parser("run", aliases=["pilotinloop"], help="PilotInLoop: run the loop for approved requirements — on a new branch created from the branch you are on",
                       description="Runs the loop on a NEW branch (default `feat/<feature>`, pattern `git.branch` in .semipilot/config.yaml), "
                                   "created from the branch that is checked out when you start. Check out the base branch first (usually main); "
                                   "the branch of an earlier run is refused unless --stack.")
    p.add_argument("feature")
    p.add_argument("--no-questions", action="store_true", help="skip the planner's questions (assumptions get logged instead)")
    p.add_argument("--branch", help="name of the branch to create (overrides `git.branch` for this run)")
    p.add_argument("--stack", action="store_true", help="allow starting from the branch of an earlier run (build this feature on top of that one)")
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

    p = sub.add_parser("kb", help="the knowledge layer: init | validate | index | resolve | drift | guard | catchup",
                       description="`semipilot kb init [--system <prefix>] [--force]` installs the knowledge layer; every other "
                                   "subcommand runs scripts/kb/kb.py (see `semipilot kb --help-tool`).")
    p.add_argument("kb_args", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_kb)

    p = sub.add_parser("config", help="print the effective configuration")
    p.set_defaults(fn=cmd_config)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
