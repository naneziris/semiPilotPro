#!/usr/bin/env python3
"""Scan a repo for package manifests and emit a dependency map.

Supports package.json, pyproject.toml, go.mod, Cargo.toml.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCAN_DIRS = ["packages", "apps", "libs", "services"]
MANIFESTS = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"]


def find_manifests(root: Path):
    found = []
    for m in MANIFESTS:
        top = root / m
        if top.exists():
            found.append(top)
    for d in SCAN_DIRS:
        base = root / d
        if not base.exists():
            continue
        for m in MANIFESTS:
            for path in base.rglob(m):
                if any(part in {"node_modules", ".git", "dist", "build", ".venv"} for part in path.parts):
                    continue
                found.append(path)
    return found


def parse_package_json(path: Path, root: Path):
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    name = data.get("name", path.parent.name)
    deps = set(data.get("dependencies", {}).keys()) | set(data.get("devDependencies", {}).keys())
    return {
        "name": name,
        "type": "node",
        "location": str(path.parent.relative_to(root)) or ".",
        "dependencies": sorted(deps),
    }


def parse_pyproject(path: Path, root: Path):
    content = path.read_text(errors="replace")
    name_match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    name = name_match.group(1) if name_match else path.parent.name
    dep_block = re.search(r"dependencies\s*=\s*\[([^\]]*)\]", content, re.DOTALL)
    deps = []
    if dep_block:
        for line in dep_block.group(1).splitlines():
            m = re.search(r'["\']([a-zA-Z0-9_\-]+)', line)
            if m:
                deps.append(m.group(1))
    return {
        "name": name,
        "type": "python",
        "location": str(path.parent.relative_to(root)) or ".",
        "dependencies": sorted(set(deps)),
    }


def parse_go_mod(path: Path, root: Path):
    content = path.read_text(errors="replace")
    name_match = re.match(r"^module\s+(\S+)", content)
    name = name_match.group(1) if name_match else path.parent.name
    deps = re.findall(r"^\s*(\S+)\s+v\S+", content, re.MULTILINE)
    return {
        "name": name,
        "type": "go",
        "location": str(path.parent.relative_to(root)) or ".",
        "dependencies": sorted(set(deps)),
    }


def parse_cargo(path: Path, root: Path):
    content = path.read_text(errors="replace")
    name_match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    name = name_match.group(1) if name_match else path.parent.name
    dep_block = re.search(r"^\[dependencies\](.*?)(?:^\[|\Z)", content, re.DOTALL | re.MULTILINE)
    deps = []
    if dep_block:
        for line in dep_block.group(1).splitlines():
            m = re.match(r"^\s*([a-zA-Z0-9_\-]+)\s*=", line)
            if m:
                deps.append(m.group(1))
    return {
        "name": name,
        "type": "rust",
        "location": str(path.parent.relative_to(root)) or ".",
        "dependencies": sorted(set(deps)),
    }


PARSERS = {
    "package.json": parse_package_json,
    "pyproject.toml": parse_pyproject,
    "go.mod": parse_go_mod,
    "Cargo.toml": parse_cargo,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a markdown map of packages and internal deps.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifests = find_manifests(root)

    if args.dry_run:
        print(f"[dry-run] Scanned {root} and {SCAN_DIRS}")
        print(f"[dry-run] Would parse {len(manifests)} manifests:")
        for m in manifests:
            print(f"[dry-run]   {m.relative_to(root)}")
        return 0

    if not manifests:
        print(f"error: no manifests found in {root}", file=sys.stderr)
        return 1

    packages = []
    for m in manifests:
        parser_fn = PARSERS.get(m.name)
        if parser_fn:
            pkg = parser_fn(m, root)
            if pkg:
                packages.append(pkg)

    all_names = {p["name"] for p in packages}

    print(f"# Project Map — {root.name}\n")
    print(f"Scanned {len(packages)} packages.\n")
    print("| Package | Type | Location | Internal Deps | External Deps |")
    print("|---|---|---|---|---|")
    for p in sorted(packages, key=lambda x: x["location"]):
        internal = sorted(d for d in p["dependencies"] if d in all_names)
        external_count = len(p["dependencies"]) - len(internal)
        internal_str = ", ".join(f"`{d}`" for d in internal) or "—"
        print(f"| `{p['name']}` | {p['type']} | `{p['location']}` | {internal_str} | {external_count} |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
