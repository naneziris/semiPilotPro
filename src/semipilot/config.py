"""Configuration: package defaults deep-merged with the repo's `.semipilot/config.yaml`.

Users see only the short repo file; everything else has a sane default here.
"""
from __future__ import annotations

import copy
import sys
from importlib import resources
from pathlib import Path
from typing import Optional

from ._yaml import yaml

SEMIPILOT_DIR = ".semipilot"
CONFIG_FILE = "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_defaults() -> dict:
    text = resources.files("semipilot").joinpath("defaults.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_config(repo: Path, path: Optional[Path] = None) -> dict:
    """Defaults + `.semipilot/config.yaml` (if present). `_path` records where the user file is."""
    cfg = load_defaults()
    user_path = path or (Path(repo) / SEMIPILOT_DIR / CONFIG_FILE)
    user: dict = {}
    if user_path.exists():
        user = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(cfg, user)
    for section in ("models", "roles"):  # `spec-critic` was the loop's plan-fidelity critic before 0.2.1
        old = (user.get(section) or {}) if isinstance(user.get(section), dict) else {}
        if "spec-critic" in old and "plan-fidelity-critic" not in old:
            cfg[section]["plan-fidelity-critic"] = old["spec-critic"]
    cfg["_path"] = str(user_path)
    cfg["_user"] = user
    return cfg


class Layout:
    """Where semipilot keeps things inside a repo. One feature = one folder; everything human-facing is
    Markdown next to each other, everything noisy is untracked under runs/."""

    def __init__(self, repo: Path):
        self.repo = Path(repo).resolve()
        self.root = self.repo / SEMIPILOT_DIR
        self.features = self.root / "features"
        self.runs = self.root / "runs"
        self.config = self.root / CONFIG_FILE
        self.last_run = self.root / "last-run"
        self.custom_prompts = self.root / "prompts"
        self.custom_roles = self.root / "roles"

    # relative (to the repo) paths are what prompts and git see
    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.repo))

    # Artifact names are the semiPilotPro / PilotInLoop v2 names on purpose — do not rename.
    LEGACY_DIR = ".github/requirements"   # single-feature layout of the manual pipeline

    def feature_dir(self, slug: str) -> Path:
        """Per-feature folder. If the manual pipeline's single `.github/requirements/requirements.md` exists
        and the per-feature file does not, that legacy folder is used so `@refiner` output is picked up as-is."""
        new = self.features / slug
        legacy = self.repo / self.LEGACY_DIR
        if not (new / "requirements.md").exists() and (legacy / "requirements.md").exists():
            return legacy
        return new

    def requirements(self, slug: str) -> Path:
        return self.feature_dir(slug) / "requirements.md"

    def open_questions(self, slug: str) -> Path:
        return self.feature_dir(slug) / "open-questions.md"

    def decisions(self, slug: str) -> Path:
        return self.feature_dir(slug) / "decisions.md"

    def rejection_log(self, slug: str) -> Path:
        return self.feature_dir(slug) / "rejection-log.md"

    def progress(self, slug: str) -> Path:
        return self.feature_dir(slug) / "implementation-progress.json"

    def report(self, slug: str) -> Path:
        return self.feature_dir(slug) / "report.md"

    def plan_json(self, slug: str) -> Path:
        return self.feature_dir(slug) / "plan.json"

    def implementation_plan(self, slug: str) -> Path:
        return self.feature_dir(slug) / "implementation-plan.md"

    def managed_paths(self, slug: str) -> list[str]:
        """Paths the orchestrator owns; never counted in scope/diff checks, committed as state."""
        return [self.rel(self.feature_dir(slug)) + "/", self.rel(self.runs) + "/"]

    def list_features(self) -> list[str]:
        return sorted(p.name for p in self.features.iterdir() if p.is_dir()) if self.features.exists() else []

    def has_legacy_requirements(self) -> bool:
        return (self.repo / self.LEGACY_DIR / "requirements.md").exists()


KB_PY = "scripts/kb/kb.py"
KB_NODE_VALIDATE = "scripts/kb/kb-validate.mjs"
INSTRUCTION_CANDIDATES = ("AGENTS.md", ".github/copilot-instructions.md", "CLAUDE.md")


def kb_flavor(repo: Path) -> Optional[str]:
    """'python' (scripts/kb/kb.py, v0.2+), 'node' (the .mjs scripts of earlier installs) or None."""
    repo = Path(repo)
    if (repo / KB_PY).exists():
        return "python"
    if (repo / KB_NODE_VALIDATE).exists():
        return "node"
    return None


def knowledge_layer_present(repo: Path, cfg: dict) -> bool:
    """The knowledge layer (docs/cards + scripts/kb) is used when present, unless the config says otherwise."""
    mode = str((cfg.get("knowledge_layer") or {}).get("mode", "auto")).lower()
    if mode == "off":
        return False
    repo = Path(repo)
    present = (repo / "docs" / "cards" / "_vocabulary.md").exists() and kb_flavor(repo) is not None
    return present or mode == "on"


def python_cmd() -> str:
    """The interpreter running semipilot, quoted for a shell command line."""
    exe = sys.executable or "python3"
    return f'"{exe}"' if " " in exe else exe


def kb_commands(repo: Path, cfg: dict) -> tuple[str, str]:
    """(validate command, resolve command with a {tags} placeholder), honouring explicit config values."""
    kl = cfg.get("knowledge_layer") or {}
    flavor = kb_flavor(repo)
    if flavor == "node":
        auto_v, auto_r = "node scripts/kb/kb-validate.mjs", "node scripts/kb/kb-resolve.mjs --tags {tags}"
    else:
        auto_v, auto_r = f"{python_cmd()} {KB_PY} validate", f"{python_cmd()} {KB_PY} resolve --tags {{tags}}"
    v = kl.get("validate_cmd") or "auto"
    r = kl.get("resolve_cmd") or "auto"
    return (auto_v if v == "auto" else v), (auto_r if r == "auto" else r)


def instructions_file(repo: Path, cfg: dict) -> str:
    """The repository's main instructions file (relative path) — `instructions_file` in the config, or the first of
    AGENTS.md, .github/copilot-instructions.md, CLAUDE.md that exists (AGENTS.md when none does)."""
    explicit = cfg.get("instructions_file")
    if explicit and explicit != "auto":
        return str(explicit)
    for cand in INSTRUCTION_CANDIDATES:
        if (Path(repo) / cand).exists():
            return cand
    return "AGENTS.md"


def legacy_config_notes(cfg: dict) -> list[str]:
    """Keys from a v0.1 `.semipilot/config.yaml` that no longer do anything, with what replaced them."""
    user = cfg.get("_user") or {}
    r = user.get("runner") or {}
    notes = []
    if "agents" in r:
        notes.append("runner.agents is ignored since v0.2: role prompts are inlined into every call (no --agent); "
                     "override a role with .semipilot/roles/<role>.md")
    if "allow_tools" in r or "deny_tools" in r:
        notes.append("runner.allow_tools / runner.deny_tools are ignored since v0.2: use harnesses.<harness>.allow "
                     "(per permission profile) and harnesses.<harness>.deny")
    for section in ("models", "roles"):
        if isinstance(user.get(section), dict) and "spec-critic" in user[section]:
            notes.append(f"{section}.spec-critic is now {section}.plan-fidelity-critic (the loop's plan-fidelity "
                         "critic; still honoured under the old name) — rename the key")
    return notes
