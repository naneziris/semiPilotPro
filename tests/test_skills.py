"""Every skill in the pack meets the Agent Skills format and stays safe to share."""
import re
from pathlib import Path

import pytest

from semipilot._yaml import yaml
from semipilot.skills_pack import SKILLS, skills_root

ROOT = skills_root()
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ""}
LINK_RE = re.compile(r"\]\(([^)#\s]+)\)")


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, f"{path} has no frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_pack_is_complete():
    assert sorted(p.name for p in ROOT.iterdir() if p.is_dir()) == sorted(SKILLS)


@pytest.mark.parametrize("name", SKILLS)
def test_frontmatter_follows_the_standard(name):
    fm, body = frontmatter(ROOT / name / "SKILL.md")
    assert fm["name"] == name and NAME_RE.match(name) and len(name) <= 64
    assert 50 <= len(fm["description"]) <= 1024
    assert "Use when" in fm["description"]  # written as a trigger
    assert set(fm) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools", "argument-hint"}
    assert len(str(fm.get("compatibility", ""))) <= 500
    assert fm["license"] == "MIT" and fm["metadata"]["version"]
    assert len((ROOT / name / "SKILL.md").read_text(encoding="utf-8").splitlines()) < 500


@pytest.mark.parametrize("name", SKILLS)
def test_supporting_files_and_links(name):
    d = ROOT / name
    assert (d / "README.md").exists(), "README.md for users"
    assert (d / "references").is_dir() or (d / "examples").is_dir(), "at least one reference or example"
    for md in d.rglob("*.md"):
        for link in LINK_RE.findall(md.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            assert (md.parent / link).exists(), f"{md.relative_to(ROOT)} links to missing {link}"


@pytest.mark.parametrize("name", SKILLS)
def test_skill_files_are_safe_to_share(name):
    for p in (ROOT / name).rglob("*"):
        assert not p.is_symlink(), f"symlink: {p}"
        assert p.name not in (".DS_Store", "Thumbs.db") and "__pycache__" not in p.parts
        if p.is_file():
            assert p.suffix in TEXT_SUFFIXES, f"non-text file: {p}"
            text = p.read_text(encoding="utf-8")  # text only, valid UTF-8
            assert not re.search(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", text), f"secret-like string in {p}"


def test_kb_script_has_shebang_header_and_no_third_party_imports():
    src = (ROOT / "semipilot-knowledge/scripts/kb.py").read_text(encoding="utf-8")
    assert src.startswith("#!/usr/bin/env python3\n") and "Usage" in src and "Security" in src
    imports = set(re.findall(r"^(?:from|import) ([a-z_]+)", src, re.MULTILINE))
    assert imports <= {"__future__", "argparse", "ast", "json", "os", "re", "subprocess", "sys", "dataclasses", "pathlib", "typing"}


def test_versions_agree_everywhere():
    import json
    from semipilot import __version__
    repo = ROOT.parent if (ROOT.parent / ".claude-plugin").exists() else None
    for name in SKILLS:
        assert frontmatter(ROOT / name / "SKILL.md")[0]["metadata"]["version"] == __version__
    if repo:  # running from a checkout: the plugin manifests ship with the repository
        plugin = json.loads((repo / ".claude-plugin/plugin.json").read_text())
        market = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
        assert plugin["name"] == "semipilot" and plugin["version"] == __version__
        assert market["plugins"][0]["version"] == __version__ and market["plugins"][0]["source"] == "./"
