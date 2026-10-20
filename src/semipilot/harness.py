"""Harness adapters: the only code that knows which agent CLI runs the loop.

The orchestrator speaks in *roles* (planner, spec-critic, plan-critic, test-writer, test-fixer, implementer,
health) and *permission profiles* (`read`, `write`, `none`). An adapter turns one role call into one fresh,
non-interactive process of its CLI and turns the CLI's output back into the agent's answer:

    adapter.command(role, profile, prompt, log_dir, extra) -> (argv, stdin_text | None)
    adapter.response(stdout)                               -> (text, meta)

Everything harness-specific that a user might need to change — the executable, tool allow/deny rules per profile,
failure patterns — lives in `defaults.yaml` under `harnesses.<name>` and can be overridden in
`.semipilot/config.yaml`. Adding a harness = one subclass + one config block (see docs/architecture.md).

Guarantees every adapter keeps (tested):
- one fresh session per call: session/resume flags are refused (`forbidden_flags`);
- no permission bypass: flags that disable the allow/deny rules are refused;
- read-only roles cannot edit files; write roles cannot push, reset, clean, switch branches or reach the network.
"""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from typing import Optional

ROLES = ("planner", "spec-critic", "plan-critic", "test-writer", "test-fixer", "implementer", "health")
PROFILES = ("read", "write", "none")


class ForbiddenFlagError(ValueError):
    pass


class UnknownHarnessError(ValueError):
    pass


@dataclass
class Invocation:
    argv: list
    stdin: Optional[str] = None


class Harness:
    """Base adapter. Subclasses set the class attributes and implement `_command` (and `response` if the CLI
    wraps its answer, e.g. in JSON)."""

    name = ""
    label = ""
    default_command = ""
    install_hint = ""
    login_hint = ""
    # Flags that would resume a session or bypass the permission rules. Merged with `runner.forbidden_flags`.
    hard_forbidden: tuple = ()

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.rcfg = cfg.get("runner") or {}
        self.hcfg = (cfg.get("harnesses") or {}).get(self.name) or {}

    # ------------------------------------------------------------------ config helpers
    @property
    def executable(self) -> list:
        cmd = self.rcfg.get("command") or self.hcfg.get("command") or self.default_command
        return shlex.split(cmd, posix=os.name != "nt") if isinstance(cmd, str) else list(cmd)  # keep C:\ paths

    def allow(self, profile: str) -> list:
        return list((self.hcfg.get("allow") or {}).get(profile) or [])

    def deny(self) -> list:
        return list(self.hcfg.get("deny") or [])

    def failure_patterns(self) -> dict:
        """The harness's own patterns plus the user's top-level `failure_patterns` (extra regexes per class)."""
        own = self.hcfg.get("failure_patterns") or {}
        extra = self.cfg.get("failure_patterns") or {}
        return {k: list(own.get(k) or []) + list(extra.get(k) or []) for k in set(own) | set(extra)}

    def model_for(self, role: str) -> str:
        """`models.<role>` if set, else `runner.model`, else '' (the CLI's default)."""
        return str((self.cfg.get("models") or {}).get(role) or self.rcfg.get("model") or "")

    def forbidden(self) -> set:
        return set(self.hard_forbidden) | set(self.rcfg.get("forbidden_flags") or []) | set(self.hcfg.get("forbidden_flags") or [])

    # ------------------------------------------------------------------ public API
    def command(self, role: str, profile: str, prompt: str, log_dir: str, extra: Optional[list] = None) -> Invocation:
        if profile not in PROFILES:
            raise ValueError(f"unknown permission profile {profile!r} for role {role!r}")
        inv = self._command(role, profile, prompt, log_dir)
        inv.argv += list(self.hcfg.get("extra_flags") or []) + list(self.rcfg.get("extra_flags") or []) + list(extra or [])
        self.guard(inv.argv, prompt)
        return inv

    def health(self, prompt: str, log_dir: str) -> Invocation:
        return self.command("health", "none", prompt, log_dir)

    def response(self, stdout: str) -> tuple[str, dict]:
        """(the agent's answer, metadata such as cost). Plain-text CLIs return stdout as-is."""
        return stdout, {}

    def classify_meta(self, meta: dict) -> Optional[str]:
        """A failure class from structured output, when the CLI reports one (None = fall back to the patterns).
        Returns one of the runner's kinds: task_failure | transient | fatal | quota_exhausted."""
        return None

    def guard(self, argv: list, prompt: str) -> None:
        forbidden = self.forbidden()
        for arg in argv[1:]:
            if arg == prompt:
                continue
            for f in forbidden:
                if arg == f or arg.startswith(f + "="):
                    raise ForbiddenFlagError(
                        f"refusing to build a {self.label} command line containing {f!r}: one fresh session per call "
                        "with the permission rules in force is a hard requirement")

    def _command(self, role: str, profile: str, prompt: str, log_dir: str) -> Invocation:  # pragma: no cover
        raise NotImplementedError


class CopilotHarness(Harness):
    """GitHub Copilot CLI: `copilot -p <prompt> -s --no-ask-user` with `--allow-tool` / `--deny-tool` rules."""

    name = "copilot"
    label = "GitHub Copilot CLI"
    default_command = "copilot"
    install_hint = "install the GitHub Copilot CLI (https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli) and run `copilot login`"
    login_hint = "copilot login"
    hard_forbidden = ("--resume", "--continue", "--session-id", "-r", "--allow-all-tools", "--allow-all-paths",
                      "--allow-all", "--yolo")

    def _command(self, role, profile, prompt, log_dir):
        argv = self.executable + ["-p", prompt, "-s", "--no-ask-user"]
        if self.model_for(role):
            argv += ["--model", self.model_for(role)]
        argv += [f"--allow-tool={t}" for t in self.allow(profile)]
        argv += [f"--deny-tool={t}" for t in self.deny()]
        argv += ["--log-dir", str(log_dir)]
        return Invocation(argv)


class ClaudeCodeHarness(Harness):
    """Claude Code: `claude -p --output-format json` with the prompt on stdin, `--permission-mode dontAsk` (anything
    not explicitly allowed is denied, never prompted) and `--allowedTools` / `--disallowedTools` rules (deny wins)."""

    name = "claude"
    label = "Claude Code"
    default_command = "claude"
    install_hint = "install Claude Code (https://code.claude.com/docs) and log in once with `claude`"
    login_hint = "claude  (then /login)"
    hard_forbidden = ("--resume", "-r", "--continue", "-c", "--session-id", "--fork-session",
                      "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions")

    def _command(self, role, profile, prompt, log_dir):
        mode = (self.hcfg.get("permission_mode") or {}).get(profile) or "dontAsk"
        if mode == "bypassPermissions":
            raise ForbiddenFlagError("permission_mode bypassPermissions would disable the deny rules; not allowed")
        argv = self.executable + ["-p", "--output-format", "json", "--no-session-persistence", "--permission-mode", mode]
        if self.hcfg.get("bare"):  # smaller startup context per call; needs ANTHROPIC_API_KEY (no subscription login)
            argv += ["--bare"]
        if self.model_for(role):
            argv += ["--model", self.model_for(role)]
        max_turns = (self.hcfg.get("max_turns") or {}).get(profile)
        if max_turns:
            argv += ["--max-turns", str(max_turns)]
        budget = self.hcfg.get("max_budget_usd_per_call")
        if budget:
            argv += ["--max-budget-usd", str(budget)]
        sources = self.hcfg.get("setting_sources")
        if sources is not None:  # "" = ignore user/project/local settings, so their allow rules cannot widen a profile
            argv += ["--setting-sources", str(sources)]
        allow = self.allow(profile)
        if allow:
            argv += ["--allowedTools", *allow]
        deny = self.deny() + self.state_dir_rules()
        if deny:
            argv += ["--disallowedTools", *deny]
        return Invocation(argv, stdin=prompt)

    def state_dir_rules(self) -> list:
        """Deny file tools on the orchestrator's state dir (plan.json lives there during a run). Claude Code's file
        rules are path-scoped: `~/…` is the home directory, `//…` an absolute path."""
        sd = str(self.cfg.get("state_dir") or "~/.semipilot/state").rstrip("/")
        if sd.startswith("~/"):
            pattern = sd
        elif sd.startswith("/"):
            pattern = "/" + sd
        else:
            return []
        return [f"Read({pattern}/**)", f"Edit({pattern}/**)"]

    def response(self, stdout: str) -> tuple[str, dict]:
        """`--output-format json` prints one JSON object whose `result` is the agent's answer. Parse defensively: the
        documented fields are `result`, `session_id` and `total_cost_usd`; `is_error`, `subtype`, `num_turns`,
        `api_error_status` and `permission_denials` were observed on Claude Code 2.1.304 and are used when present."""
        text = stdout.strip()
        obj = None
        try:
            obj = json.loads(text)
        except ValueError:
            # tolerate leading noise: take the last line that parses as a JSON object
            for line in reversed(text.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        obj = json.loads(line)
                        break
                    except ValueError:
                        continue
        if not isinstance(obj, dict):
            return stdout, {}
        if isinstance(obj.get("result"), str):
            answer = obj["result"]
        elif obj.get("structured_output") is not None:
            answer = json.dumps(obj["structured_output"])
        else:
            answer = ""
        meta = {k: obj[k] for k in ("is_error", "subtype", "total_cost_usd", "num_turns", "api_error_status") if k in obj}
        if isinstance(obj.get("permission_denials"), list):
            meta["permission_denials"] = len(obj["permission_denials"])
        if obj.get("errors"):
            errs = obj["errors"]
            meta["errors"] = "\n".join(map(str, errs)) if isinstance(errs, list) else str(errs)
        return answer, meta

    def classify_meta(self, meta: dict) -> Optional[str]:
        """Claude Code reports why a call failed: `subtype` error_max_turns / error_max_budget_usd are the caps the
        loop set (the task's problem, not an outage); `api_error_status` carries the HTTP status of an API failure."""
        sub = str(meta.get("subtype") or "")
        if sub.startswith("error_max"):
            return "task_failure"
        status = meta.get("api_error_status")
        try:
            status = int(status) if status is not None else None
        except (TypeError, ValueError):
            status = None
        if status in (401, 403):
            return "fatal"
        if status == 429 or (status is not None and 500 <= status <= 599):
            return "transient"
        return None


HARNESSES = {h.name: h for h in (CopilotHarness, ClaudeCodeHarness)}
ALIASES = {"copilot-cli": "copilot", "github-copilot": "copilot", "claude-code": "claude", "claudecode": "claude"}


def harness_name(cfg: dict) -> str:
    raw = str(cfg.get("harness") or "copilot").strip().lower()
    return ALIASES.get(raw, raw)


def get_harness(cfg: dict) -> Harness:
    name = harness_name(cfg)
    if name not in HARNESSES:
        raise UnknownHarnessError(f"unknown harness {name!r}; supported: {', '.join(sorted(HARNESSES))}")
    return HARNESSES[name](cfg)


def role_profile(cfg: dict, role: str) -> str:
    return str((cfg.get("roles") or {}).get(role) or ("none" if role == "health" else "read"))
