"""Chores: one small fix per run, unattended.

A feature run needs a human at both ends. A chore does not, because its gate is entirely mechanical and cheap:

    1. the project's checks pass on the starting branch (otherwise nothing is attempted);
    2. the agent makes one fix, in at most `max_files` files and `max_diff_lines` changed lines;
    3. no existing test file changed (they are all locked), no instructions or knowledge file changed;
    4. the checks still pass;
    5. when the chore has a `find` command: the finding it was given is gone and there are fewer findings than
       before — a suppression that merely hides it elsewhere, or a fix that creates a new one, does not pass.

Pass → one commit on its own branch (and, with `chores.open_mr`, one small request). Fail → the branch is deleted,
the finding is remembered, and after `skip_after_failures` attempts it is skipped. Either way the next run starts
from the same clean base and picks the next finding.

Chores never outrun the person who reads them: a finding whose fix is still on an unmerged chore branch is not
fixed a second time, and when `max_open` such branches are waiting, nothing new is attempted until one is merged
or deleted. The memory is `chores.json` in semipilot's state folder
(`state_dir`, outside the repository), so a chore never leaves a file behind in the working tree.

There is no scheduler here on purpose: `semipilot chore` is one run; cron, a CI schedule or a workflow calls it.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from . import forge, usage as usage_mod
from .config import INSTRUCTION_CANDIDATES, Layout, instructions_file, local_set, sync_excludes
from .harness import UnknownHarnessError, get_harness
from .orchestrator import _ANSI, Git, TestLock, blocked_question, render_prompt, run_checks
from .runner import HaltRun, Runner

PROTECTED = ("docs/cards/", ".github/instructions/")
HISTORY_MAX = 200


class ChoreError(Exception):
    pass


def chores_cfg(cfg: dict) -> dict:
    c = cfg.get("chores")
    return c if isinstance(c, dict) else {}


def signature(line: str) -> str:
    """A finding's identity across runs: the line with numbers removed (line numbers move when files change)."""
    norm = re.sub(r"\d+", "N", _ANSI.sub("", line)).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


class Chore:
    def __init__(self, repo: Path, cfg: dict, sleep_fn=time.sleep, now_fn=None, log_fn=None):
        self.repo = Path(repo).resolve()
        self.cfg = cfg
        self.ccfg = chores_cfg(cfg)
        self.lay = Layout(self.repo)
        self.git = Git(self.repo)
        if cfg.get("private") or (cfg.get("git") or {}).get("local_paths"):
            try:
                sync_excludes(self.repo, cfg)
            except OSError:
                pass
            self.git.local = local_set(self.repo, cfg)
        self.sleep = sleep_fn
        self.now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._log = log_fn
        base = Path(os.path.expandvars(os.path.expanduser(cfg.get("state_dir", "~/.semipilot/state"))))
        self.state_path = base / self.repo.name / "chores.json"
        self.runner: Optional[Runner] = None

    # ------------------------------------------------------------------ plumbing
    def log(self, msg: str) -> None:
        if self._log:
            self._log(msg)
        else:
            print(f"[{self.now().astimezone().strftime('%H:%M:%S')}] {msg}", flush=True)

    def items(self) -> list[dict]:
        out = []
        for it in self.ccfg.get("items") or []:
            if isinstance(it, dict) and it.get("name"):
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(it["name"])):
                    raise ChoreError(f"chore name {it['name']!r}: use lowercase letters, digits and hyphens")
                if not it.get("find") and not it.get("instruction"):
                    raise ChoreError(f"chore {it['name']}: give it a `find` command, an `instruction`, or both")
                out.append(it)
        return out

    def load_state(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("failures", {})
        state.setdefault("history", [])
        return state

    def save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state["history"] = state["history"][-HISTORY_MAX:]
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def reset_state(self, name: Optional[str] = None) -> int:
        """Forget remembered failures (all, or one chore's): skipped findings get tried again."""
        state = self.load_state()
        n = sum(len(v) for k, v in state["failures"].items() if name in (None, k))
        state["failures"] = {k: v for k, v in state["failures"].items() if name not in (None, k)}
        self.save_state(state)
        return n

    def findings(self, item: dict) -> list[str]:
        """Lines printed by the chore's `find` command (its exit code is ignored: linters exit non-zero on findings)."""
        r = subprocess.run(str(item["find"]), shell=True, cwd=self.repo, capture_output=True, text=True)
        lines = [l.rstrip() for l in _ANSI.sub("", r.stdout).splitlines() if l.strip()]
        if item.get("match"):
            pat = re.compile(str(item["match"]))
            lines = [l for l in lines if pat.search(l)]
        return lines

    def open_branches(self, state: dict) -> dict:
        """Chore branches that still wait for a human: branch → the signature of the finding fixed there. A branch
        counts as waiting while it exists locally and is not merged into the branch that is checked out."""
        out = {}
        for e in state["history"]:
            b = e.get("branch")
            if e.get("status") == "fixed" and b and self.git.branch_exists(b) and subprocess.run(
                    ["git", "merge-base", "--is-ancestor", b, "HEAD"], cwd=self.repo, capture_output=True).returncode != 0:
                out[b] = e.get("sig")
        return out

    def candidates(self, item: dict, state: dict) -> tuple[list[str], list[str]]:
        """(findings worth trying, all findings) — left out: a finding that failed too often, and one whose fix is
        already waiting on an unmerged chore branch."""
        found = self.findings(item)
        limit = int(self.ccfg.get("skip_after_failures", 2))
        failed = state["failures"].get(item["name"], {})
        waiting = set(self.open_branches(state).values())
        return [l for l in found if failed.get(signature(l), 0) < limit and signature(l) not in waiting], found

    def listing(self) -> list[dict]:
        state = self.load_state()
        out = []
        for it in self.items():
            if it.get("find"):
                todo, found = self.candidates(it, state)
                failed = state["failures"].get(it["name"], {})
                limit = int(self.ccfg.get("skip_after_failures", 2))
                skipped = sum(1 for l in found if failed.get(signature(l), 0) >= limit)
                out.append({"name": it["name"], "findings": len(found), "skipped": skipped,
                            **({"waiting": len(found) - len(todo) - skipped} if len(found) - len(todo) - skipped else {})})
            else:
                out.append({"name": it["name"], "findings": None, "skipped": 0})
        return out

    def check_names(self, item: dict) -> Optional[list[str]]:
        names = item.get("checks")
        if not names:
            return None
        known = {str(c.get("name")) for c in self.cfg.get("checks") or []}
        unknown = [n for n in names if n not in known]
        if unknown:
            raise ChoreError(f"chore {item['name']}: unknown check(s) {', '.join(unknown)} (configured: {', '.join(sorted(known))})")
        return list(names)

    def local_snapshot(self) -> dict:
        ls = self.git.local
        if not ls or not ls.user:
            return {}
        return {f: (self.repo / f).read_bytes() for f in ls.user_files()}

    def restore_local(self, snap: dict) -> list[str]:
        if not self.git.local or not self.git.local.user:
            return []
        now = self.local_snapshot()
        touched = sorted(f for f in set(snap) | set(now) if snap.get(f) != now.get(f))
        for f in touched:
            if f in snap:
                (self.repo / f).parent.mkdir(parents=True, exist_ok=True)
                (self.repo / f).write_bytes(snap[f])
            else:
                (self.repo / f).unlink(missing_ok=True)
        return touched

    def managed(self, path: str) -> bool:
        return path.startswith(self.lay.rel(self.lay.root) + "/")

    def protected(self, path: str) -> bool:
        return path in INSTRUCTION_CANDIDATES or path == instructions_file(self.repo, self.cfg) \
            or any(path.startswith(p) for p in PROTECTED)

    # ------------------------------------------------------------------ one run
    def preflight(self) -> None:
        try:
            get_harness(self.cfg)
        except UnknownHarnessError as e:
            raise ChoreError(f"{e} (set `harness:` in .semipilot/config.yaml)")
        checks = self.cfg.get("checks") or []
        if not checks or any(str(c.get("cmd", "")).lstrip().startswith("#") for c in checks):
            raise ChoreError("no usable `checks` in .semipilot/config.yaml — a chore is only as safe as the checks that gate it")
        if not self.items():
            raise ChoreError("no chores configured: add one under `chores.items` in .semipilot/config.yaml "
                             "(see docs/chores.md)")
        if self.git.current_branch() == "HEAD":
            raise ChoreError("detached HEAD; check out the branch chores should start from")
        if any(not self.managed(f) for f in self.git.status_paths()):
            raise ChoreError("working tree is dirty; a chore starts from a clean tree")

    def pick(self, name: Optional[str], state: dict) -> tuple[Optional[dict], Optional[str], list[str]]:
        """(chore, the finding to fix or None for an instruction-only chore, every finding before) — (None, None, [])
        when there is nothing to do."""
        items = self.items()
        if name:
            items = [i for i in items if i["name"] == name]
            if not items:
                raise ChoreError(f"no chore named {name!r} (configured: {', '.join(i['name'] for i in self.items())})")
        for it in items:
            if not it.get("find"):
                return it, None, []
            todo, found = self.candidates(it, state)
            if todo:
                return it, todo[0], found
        return None, None, []

    def run(self, name: Optional[str] = None, dry_run: bool = False) -> dict:
        self.preflight()
        state = self.load_state()
        waiting = self.open_branches(state)
        max_open = self.ccfg.get("max_open", 3)
        if max_open and len(waiting) >= int(max_open) and not dry_run:
            self.log(f"{len(waiting)} chore branch(es) still wait for review ({', '.join(sorted(waiting))}); nothing new "
                     f"until one is merged or deleted (chores.max_open: {max_open})")
            return {"status": "waiting_for_review", "detail": ", ".join(sorted(waiting))}
        item, target, before = self.pick(name, state)
        if item is None:
            self.log("nothing to do: no chore has a finding left to try")
            return {"status": "nothing_to_do"}
        chore = item["name"]
        sig = signature(target) if target else hashlib.sha1(self.now().isoformat().encode()).hexdigest()[:12]
        self.log(f"chore {chore}: " + (f"{len(before)} finding(s); fixing: {target}" if target else "instruction-only (no finder)"))
        if dry_run:
            return {"status": "dry_run", "chore": chore, "target": target, "findings": len(before)}

        only = self.check_names(item)
        ok, errors, _ = run_checks(self.cfg, self.repo, only=only)
        if not ok:
            self.log("the checks fail on the starting branch — nothing attempted (a chore cannot be verified on a red base)")
            return self.record(state, chore, target, "checks_fail_on_base", detail=_summarize(errors))

        base_branch, base_sha = self.git.current_branch(), self.git.head()
        branch = str(self.ccfg.get("branch") or "chore/{chore}-{date}-{id}").format(
            chore=chore, date=self.now().strftime("%Y%m%d"), id=sig[:6])
        if self.git.branch_exists(branch):
            raise ChoreError(f"branch {branch} already exists (an earlier chore run): merge or delete it first")
        run_id = f"chore-{chore}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        self.runner = Runner(self.cfg, self.lay.runs / run_id, sleep_fn=self.sleep, cwd=self.repo,
                             reset_tree_fn=lambda: self.git.reset_hard(base_sha, preserve=[self.lay.rel(self.lay.root) + "/"]))
        self.git.create_branch(branch)
        lock = TestLock(self.repo, self.cfg["tests"]["patterns"])
        known = self.git.run("ls-files", check=False).splitlines() + \
            self.git.run("ls-files", "--others", "--exclude-standard", check=False).splitlines()
        lock.lock([f for f in known if f and lock.matches(f)])  # every test file git knows about (not node_modules)
        result = {"status": "failed", "detail": ""}
        try:
            result = self.attempts(item, target, before, base_sha, branch, lock, only)
        except HaltRun as h:
            result = {"status": "halted", "detail": f"{h.reason}: {h.detail.strip().splitlines()[-1] if h.detail.strip() else ''}"}
        finally:
            if result["status"] != "fixed":
                self.abandon(base_branch, base_sha, branch)
        if result["status"] == "fixed":
            if self.ccfg.get("open_mr"):
                result["mr"] = self.open_mr(chore, target, branch, base_branch, result, run_id)
            if self.ccfg.get("return_to_base", True):
                self.git.checkout(base_branch)
        if result["status"] in ("failed", "blocked") and target:
            bump = int(self.ccfg.get("skip_after_failures", 2)) if result["status"] == "blocked" else 1
            f = state["failures"].setdefault(chore, {})
            f[sig] = f.get(sig, 0) + bump
        return self.record(state, chore, target, result["status"], detail=result.get("detail", ""), sig=sig,
                           branch=branch if result["status"] == "fixed" else None, commit=result.get("commit"),
                           mr=result.get("mr"), left=result.get("left"))

    def attempts(self, item: dict, target: Optional[str], before: list[str], base_sha: str, branch: str,
                 lock: TestLock, only: Optional[list[str]]) -> dict:
        chore = item["name"]
        max_files, max_lines = int(self.ccfg.get("max_files", 3)), int(self.ccfg.get("max_diff_lines", 80))
        main = instructions_file(self.repo, self.cfg)
        present = list(dict.fromkeys(c for c in (main, *INSTRUCTION_CANDIDATES) if (self.repo / c).exists())) or [main]
        instruction = str(item.get("instruction") or "Fix the finding below in the code itself.").strip()
        errors = None
        for attempt in range(1, int(self.ccfg.get("max_attempts", 2)) + 1):
            prompt = render_prompt("chore", self.lay.custom_prompts, chore=chore, instruction=instruction,
                                   target=target or "(no finder: find ONE instance of what the instruction describes, "
                                                    "say which one you chose, and fix only that)",
                                   max_files=str(max_files), max_diff_lines=str(max_lines),
                                   instructions=", ".join(f"`{c}`" for c in present),
                                   errors=errors or "(first attempt — no previous errors)")
            snap = self.local_snapshot()
            res = self.runner.run("chore", prompt, f"attempt{attempt}")
            touched_local = self.restore_local(snap)
            if self.git.current_branch() != branch:
                now = self.git.current_branch()
                self.git.checkout(branch)
                return {"status": "failed", "detail": f"the agent switched the branch to {now}"}
            q = blocked_question(res.text)
            if q:
                return {"status": "blocked", "detail": q}
            changed = [f for f in self.git.changed_files(base_sha) if not self.managed(f)]
            viol = lock.violations()
            bad = [f for f in changed if self.protected(f)]
            add, rem = self.git.diff_lines(base_sha, exclude=[self.lay.rel(self.lay.root) + "/"])
            if res.timed_out:
                errors = "The previous attempt timed out."
            elif touched_local:
                errors = f"You changed {', '.join(touched_local)}, which the user keeps local; that was reverted. Do not touch them."
            elif viol:
                self.git.restore_paths(base_sha, viol)
                errors = f"You modified existing test files ({', '.join(viol)}); that was reverted. Fix the code, not the tests."
            elif bad:
                self.git.restore_paths(base_sha, bad)
                errors = f"You modified {', '.join(bad)}, which a chore may not change; that was reverted."
            elif not changed:
                errors = "You changed nothing. Fix the finding, or answer `BLOCKED: <why it is not a small fix>`."
            elif len(changed) > max_files:
                errors = (f"You changed {len(changed)} files ({', '.join(changed)}); the limit is {max_files}. Undo everything "
                          "that is not needed for this one finding.")
            elif add + rem > max_lines:
                errors = f"Your change is {add + rem} lines; the limit is {max_lines}. Make the smallest fix, or answer BLOCKED."
            else:
                ok, check_errors, _ = run_checks(self.cfg, self.repo, only=only)
                if not ok:
                    errors = check_errors
                else:
                    left, errors = None, None
                    if target:
                        after = self.findings(item)
                        left, sig = len(after), signature(target)
                        if sum(1 for l in after if signature(l) == sig) >= sum(1 for l in before if signature(l) == sig):
                            errors = f"The finding is still reported by `{item['find']}`:\n{target}"
                        elif left >= len(before):
                            errors = (f"The finding is gone, but `{item['find']}` now reports {left} finding(s) (it was "
                                      f"{len(before)}): your change introduced a new one. Fix that too, within the same limits.")
                    if errors is None:
                        subject = self.subject(chore, target, changed)
                        sha = self.git.commit(self.commit_message(chore, subject), exclude=[self.lay.rel(self.lay.root) + "/"])
                        self.log(f"chore {chore}: fixed → {sha[:8]} on {branch} ({len(changed)} file(s), +{add}/-{rem})")
                        return {"status": "fixed", "commit": sha, "files": changed, "added": add, "removed": rem, "left": left}
            self.log(f"chore {chore}: attempt {attempt} did not pass — {_summarize(errors)}")
        return {"status": "failed", "detail": _summarize(errors)}

    def subject(self, chore: str, target: Optional[str], changed: list[str]) -> str:
        if target:
            return ("fix " + re.sub(r"\s+", " ", target).strip())[:100]
        return f"one {chore} fix in {changed[0]}" + (f" and {len(changed) - 1} more" if len(changed) > 1 else "")

    def commit_message(self, chore: str, subject: str) -> str:
        g = self.cfg.get("git") or {}
        template = g.get("commit") or "{type}({feature}): {subject}"
        return template.format(type="chore", feature=chore, subject=subject)

    def abandon(self, base_branch: str, base_sha: str, branch: str) -> None:
        """Leave no trace of a chore that did not pass: back to the base branch, the chore branch deleted."""
        try:
            if self.git.current_branch() == branch:
                self.git.reset_hard(base_sha, preserve=[self.lay.rel(self.lay.root) + "/"])
            self.git.checkout(base_branch)
            if self.git.branch_exists(branch):
                self.git.run("branch", "-D", branch, check=False)
        except RuntimeError as e:
            self.log(f"could not clean up after the chore: {e}")

    def open_mr(self, chore: str, target: Optional[str], branch: str, base_branch: str, result: dict, run_id: str) -> str:
        body = "\n".join([
            f"One small `{chore}` fix, made unattended by `semipilot chore`.", "",
            f"- Finding: `{target}`" if target else f"- Chore: {chore} (no finder)",
            f"- Files: {', '.join('`' + f + '`' for f in result.get('files', []))} (+{result.get('added', 0)}/-{result.get('removed', 0)})",
            "- Gate: the project's checks pass; no existing test changed"
            + ("; the finding is gone and no new one appeared" if target else ""), ""])
        base = str(forge.forge_cfg(self.cfg).get("base") or base_branch)
        try:
            url = forge.open_request(self.cfg, self.repo, branch, base, self.git.run("log", "-1", "--format=%s").strip(),
                                     body, self.lay.runs / run_id, log=self.log)
            self.log(f"chore {chore}: request opened → {url}")
            return url or ""
        except forge.ForgeError as e:
            self.log(f"chore {chore}: the fix is committed on {branch}, but no request was opened: {e}")
            return ""

    def record(self, state: dict, chore: str, target: Optional[str], status: str, detail: str = "", **extra) -> dict:
        entry = {"at": self.now().isoformat(), "chore": chore, "target": target, "status": status}
        if detail:
            entry["detail"] = detail[:400]
        entry.update({k: v for k, v in extra.items() if v not in (None, "")})
        if self.runner:
            entry["usage"] = self.runner.ledger.summary()["total"]
        state["history"].append(entry)
        self.save_state(state)
        return entry


def _summarize(errors: Optional[str]) -> str:
    if not errors:
        return ""
    lines = [l for l in errors.splitlines() if l.strip() and not l.startswith("###")]
    return " | ".join(lines[:3])[:400]


def describe(entry: dict, premium_request_usd: Optional[float] = None) -> str:
    """One line for the terminal and for `semipilot chore --history`."""
    words = {"fixed": "fixed", "nothing_to_do": "nothing to do", "failed": "did not pass its gate — nothing kept",
             "blocked": "not a small fix — skipped from now on", "halted": "the agent could not run",
             "checks_fail_on_base": "the checks fail on the starting branch — nothing attempted", "dry_run": "dry run",
             "waiting_for_review": "earlier chore branches still wait for review — nothing new attempted"}
    line = f"{entry.get('chore', '')}: {words.get(entry['status'], entry['status'])}".lstrip(": ")
    if entry.get("target"):
        line += f" — {entry['target'][:120]}"
    if entry.get("branch"):
        line += f" → {entry['branch']}" + (f" ({entry['commit'][:8]})" if entry.get("commit") else "")
    if entry.get("mr"):
        line += f" → {entry['mr']}"
    if entry.get("detail") and entry["status"] != "fixed":
        line += f" [{entry['detail'][:160]}]"
    if entry.get("usage", {}).get("calls"):
        line += f" ({usage_mod.describe(entry['usage'], premium_request_usd)})"
    return line
