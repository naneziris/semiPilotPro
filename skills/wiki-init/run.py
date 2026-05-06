#!/usr/bin/env python3
"""Scaffold the .wiki/ directory for SemiPilot Pro.

Creates seven structured markdown files following the Karpathy wiki pattern.
Seeds OVERVIEW.md and DATA_MODELS.md from detected project metadata.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

WIKI_FILES = [
    "OVERVIEW.md",
    "ARCH_DECISIONS.md",
    "DATA_MODELS.md",
    "PATTERNS.md",
    "DEPENDENCIES.md",
    "API.md",
    "CHANGELOG.md",
]

TEMPLATE = """# {title}

## Summary
{summary}

## Tags
{tags}

## Context
{context}

## Entries
{entries}

## Last Updated
{date} — wiki-init
"""

CHANGELOG_TEMPLATE = """# Changelog

All notable user-facing changes to this project land here. Scribe appends one line per shipped RPI cycle.

Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]
### Added
### Changed
### Fixed
### Deprecated
### Removed

## Last Updated
{date} — wiki-init
"""

FILE_META = {
    "OVERVIEW.md": {
        "title": "Overview",
        "summary": "Tech stack, project purpose, and team conventions.",
        "tags": "`project`, `stack`, `conventions`",
        "context": "This is the top-level orientation file. New agents and engineers read this first.",
    },
    "ARCH_DECISIONS.md": {
        "title": "Architecture Decisions",
        "summary": "Architecture Decision Records — why we chose X over Y.",
        "tags": "`adr`, `architecture`",
        "context": "Every non-trivial architectural choice gets an ADR here. Scribe appends on every approved implementation plan that authorized one.",
    },
    "DATA_MODELS.md": {
        "title": "Data Models",
        "summary": "Schemas, key types, and their relationships.",
        "tags": "`schema`, `database`, `types`",
        "context": "Spec-critic reads this to check feasibility. Keep schema changes current here or Gate 1 will reject specs as unverifiable.",
    },
    "PATTERNS.md": {
        "title": "Code Patterns",
        "summary": "Naming conventions, DI patterns, error handling, and test standards.",
        "tags": "`conventions`, `testing`, `patterns`",
        "context": "Pattern-critic reads this to approve or reject diffs. Every accepted convention in this codebase is documented here.",
    },
    "DEPENDENCIES.md": {
        "title": "Dependencies",
        "summary": "Current, deprecated, and banned libraries.",
        "tags": "`dependencies`, `libraries`",
        "context": "Planner checks this before proposing new libraries. Pattern-critic rejects diffs that use deprecated or banned entries.",
    },
    "API.md": {
        "title": "Public API",
        "summary": "Public API signatures and contracts.",
        "tags": "`api`, `contracts`",
        "context": "Breaking changes to anything listed here require an authorized plan entry. Pattern-critic cross-checks diffs against this file.",
    },
}


def detect_stack(root: Path) -> dict:
    """Best-effort detection of project stack from manifest files."""
    info = {"languages": [], "frameworks": [], "manifests": []}

    if (root / "package.json").exists():
        info["manifests"].append("package.json")
        try:
            pkg = json.loads((root / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            info["languages"].append("TypeScript/JavaScript")
            if "react" in deps:
                info["frameworks"].append("React")
            if "next" in deps:
                info["frameworks"].append("Next.js")
            if "express" in deps:
                info["frameworks"].append("Express")
            if "fastify" in deps:
                info["frameworks"].append("Fastify")
        except (json.JSONDecodeError, OSError):
            pass

    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        info["manifests"].append("pyproject.toml" if (root / "pyproject.toml").exists() else "requirements.txt")
        info["languages"].append("Python")

    if (root / "go.mod").exists():
        info["manifests"].append("go.mod")
        info["languages"].append("Go")

    if (root / "Cargo.toml").exists():
        info["manifests"].append("Cargo.toml")
        info["languages"].append("Rust")

    return info


def detect_schemas(root: Path) -> list:
    """Find likely schema files without reading their full content."""
    candidates = []
    for pattern in ["schema.prisma", "*.sql", "models.py", "schema.py", "entities.ts"]:
        for path in root.rglob(pattern):
            if any(part in {"node_modules", ".git", "dist", "build", ".venv"} for part in path.parts):
                continue
            candidates.append(str(path.relative_to(root)))
    return candidates[:20]


def build_overview_entries(root: Path) -> str:
    stack = detect_stack(root)
    if not stack["languages"] and not stack["manifests"]:
        return "_No project manifests detected. Scribe should populate this after the first RPI cycle._"

    lines = ["### Auto-detected stack (verify and refine)"]
    if stack["languages"]:
        lines.append(f"- **Languages:** {', '.join(stack['languages'])}")
    if stack["frameworks"]:
        lines.append(f"- **Frameworks:** {', '.join(stack['frameworks'])}")
    if stack["manifests"]:
        lines.append(f"- **Manifests:** {', '.join(stack['manifests'])}")
    return "\n".join(lines)


def build_data_model_entries(root: Path) -> str:
    schemas = detect_schemas(root)
    if not schemas:
        return "_No schema files auto-detected. Scribe must populate this on first data-model change._"
    lines = ["### Auto-detected schema files (stub — scribe should document)"]
    for s in schemas:
        lines.append(f"- `{s}`")
    return "\n".join(lines)


def render(name: str, root: Path, today: str) -> str:
    if name == "CHANGELOG.md":
        return CHANGELOG_TEMPLATE.format(date=today)

    meta = FILE_META[name]
    if name == "OVERVIEW.md":
        entries = build_overview_entries(root)
    elif name == "DATA_MODELS.md":
        entries = build_data_model_entries(root)
    else:
        entries = "_No entries yet. Scribe appends as features land._"

    return TEMPLATE.format(
        title=meta["title"],
        summary=meta["summary"],
        tags=meta["tags"],
        context=meta["context"],
        entries=entries,
        date=today,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold .wiki/ for SemiPilot Pro.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written, don't touch disk.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing wiki files.")
    parser.add_argument("--root", default=".", help="Repo root (default: current directory).")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wiki_dir = root / ".wiki"
    today = date.today().isoformat()

    actions = []
    for name in WIKI_FILES:
        target = wiki_dir / name
        content = render(name, root, today)
        if target.exists() and not args.force:
            actions.append(("skip", target, None))
        else:
            actions.append(("write", target, content))

    if args.dry_run:
        print(f"[dry-run] Would operate on: {wiki_dir}")
        for action, target, content in actions:
            rel = target.relative_to(root)
            if action == "skip":
                print(f"[dry-run] skip   {rel} (already exists; use --force to overwrite)")
            else:
                print(f"[dry-run] write  {rel} ({len(content.splitlines())} lines)")
        return 0

    wiki_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for action, target, content in actions:
        rel = target.relative_to(root)
        if action == "skip":
            print(f"skip   {rel}")
            skipped += 1
        else:
            target.write_text(content)
            print(f"write  {rel}")
            written += 1

    print(f"\nDone. {written} written, {skipped} skipped.")
    if skipped and not args.force:
        print("Re-run with --force to overwrite skipped files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
