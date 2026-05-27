#!/usr/bin/env python3
"""
patterns-seed — infer naming, DI, error-handling, and test conventions from
an existing codebase and seed .wiki/PATTERNS.md so the Pattern Critic has
something to enforce on the first cycle.

Best-effort heuristics. Not a substitute for human review by @scribe.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

SUPPORTED_EXTS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
}

IGNORED_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "dist", "build", "out", "target", ".next", ".turbo",
    "coverage", ".idea", ".vscode", "vendor",
}

TEST_FILE_PATTERNS = [
    (re.compile(r".*\.test\.(t|j)sx?$"), "*.test.ts(x) / *.test.js(x)"),
    (re.compile(r".*\.spec\.(t|j)sx?$"), "*.spec.ts(x) / *.spec.js(x)"),
    (re.compile(r"^test_.*\.py$"), "test_*.py"),
    (re.compile(r".*_test\.py$"), "*_test.py"),
    (re.compile(r".*_test\.go$"), "*_test.go"),
    (re.compile(r".*Test\.java$"), "*Test.java"),
    (re.compile(r".*Tests\.cs$"), "*Tests.cs"),
    (re.compile(r".*_spec\.rb$"), "*_spec.rb"),
]

CASE_PATTERNS = {
    "kebab-case": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$"),
    "snake_case": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
    "SCREAMING_SNAKE": re.compile(r"^[A-Z0-9]+(_[A-Z0-9]+)+$"),
}


def detect_case(name: str) -> str | None:
    base = name
    for style, pattern in CASE_PATTERNS.items():
        if pattern.match(base):
            return style
    return None


def find_source_files(root: Path) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext in SUPPORTED_EXTS:
                files.append(Path(dirpath) / filename)
    return files


def sample_files(files: list[Path], n: int) -> list[Path]:
    if len(files) <= n:
        return files
    random.seed(42)
    return random.sample(files, n)


def infer_file_naming(files: list[Path]) -> Counter:
    counter: Counter[str] = Counter()
    for f in files:
        stem = f.stem
        # Strip test suffix for naming analysis
        stem = re.sub(r"\.(test|spec)$", "", stem)
        stem = re.sub(r"^test_|_test$", "", stem)
        case = detect_case(stem)
        if case:
            counter[case] += 1
    return counter


def infer_test_conventions(files: list[Path]) -> tuple[Counter, set[str]]:
    counter: Counter[str] = Counter()
    frameworks: set[str] = set()
    for f in files:
        name = f.name
        for pattern, label in TEST_FILE_PATTERNS:
            if pattern.match(name):
                counter[label] += 1
                break
    # Detect frameworks from package.json / pyproject if present
    return counter, frameworks


def detect_frameworks(root: Path) -> set[str]:
    frameworks: set[str] = set()
    pkg = root / "package.json"
    if pkg.exists():
        try:
            content = pkg.read_text(encoding="utf-8", errors="ignore")
            for fw, key in [
                ("Jest", "jest"),
                ("Vitest", "vitest"),
                ("Mocha", "mocha"),
                ("Playwright", "@playwright/test"),
                ("Cypress", "cypress"),
                ("NestJS", "@nestjs/"),
                ("React", "\"react\""),
                ("Next.js", "\"next\""),
                ("Express", "\"express\""),
                ("Fastify", "\"fastify\""),
            ]:
                if key in content:
                    frameworks.add(fw)
        except Exception:
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            for fw, key in [
                ("pytest", "pytest"),
                ("Django", "django"),
                ("FastAPI", "fastapi"),
                ("Flask", "flask"),
            ]:
                if key in content.lower():
                    frameworks.add(fw)
        except Exception:
            pass
    return frameworks


def infer_imports(files: list[Path]) -> dict[str, int]:
    counts = {"relative": 0, "absolute": 0, "barrel": 0}
    barrel_pattern = re.compile(r"from\s+['\"][^'\"]*?/index['\"]")
    rel_pattern = re.compile(r"(from|import)\s+['\"]\.{1,2}/")
    abs_pattern = re.compile(r"(from|import)\s+['\"](?![./])[a-zA-Z@]")
    for f in files:
        if f.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        counts["relative"] += len(rel_pattern.findall(content))
        counts["absolute"] += len(abs_pattern.findall(content))
        counts["barrel"] += len(barrel_pattern.findall(content))
    return counts


def infer_error_handling(files: list[Path]) -> Counter:
    counter: Counter[str] = Counter()
    throw_re = re.compile(r"\bthrow\s+new\s+")
    result_re = re.compile(r"\bResult<|\bResult\.(Ok|Err)|\bResult\.|\bResultAsync<")
    try_re = re.compile(r"\btry\s*\{|\btry:")
    option_re = re.compile(r"\bOption<|\bSome\(|\bNone\b")
    rescue_re = re.compile(r"\brescue\b")
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if throw_re.search(content):
            counter["throw / exceptions"] += 1
        if result_re.search(content):
            counter["Result types"] += 1
        if try_re.search(content):
            counter["try / try-except blocks"] += 1
        if option_re.search(content):
            counter["Option / Maybe types"] += 1
        if rescue_re.search(content):
            counter["rescue (Ruby)"] += 1
    return counter


def infer_di_style(files: list[Path]) -> Counter:
    counter: Counter[str] = Counter()
    nestjs_re = re.compile(r"@(Injectable|Inject|Module)\b")
    spring_re = re.compile(r"@(Autowired|Component|Service|Repository)\b")
    ctor_inject_re = re.compile(r"constructor\s*\([^)]*private\s+(readonly\s+)?\w+")
    factory_re = re.compile(r"\bcreate[A-Z]\w*\(|\bmake[A-Z]\w*\(")
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if nestjs_re.search(content):
            counter["NestJS decorators (@Injectable, @Inject)"] += 1
        if spring_re.search(content):
            counter["Spring decorators (@Autowired, @Service)"] += 1
        if ctor_inject_re.search(content):
            counter["TypeScript constructor injection"] += 1
        if factory_re.search(content):
            counter["Factory functions (create*, make*)"] += 1
    return counter


def top_n(counter: Counter, n: int = 3) -> list[tuple[str, int]]:
    return counter.most_common(n)


def format_section(title: str, counter: Counter, empty_msg: str) -> str:
    if not counter:
        return f"### {title}\n\n{empty_msg}\n"
    lines = [f"### {title}", ""]
    total = sum(counter.values())
    for label, count in top_n(counter, 5):
        pct = round((count / total) * 100) if total else 0
        lines.append(f"- **{label}** — {count} occurrences ({pct}%)")
    dominant = counter.most_common(1)[0][0]
    lines.append(f"\n**Dominant style:** `{dominant}`")
    return "\n".join(lines) + "\n"


def build_patterns_md(
    root: Path,
    file_naming: Counter,
    test_naming: Counter,
    imports: dict[str, int],
    error_handling: Counter,
    di_style: Counter,
    frameworks: set[str],
    sampled_count: int,
    total_count: int,
) -> str:
    today = date.today().isoformat()
    imports_section_lines = []
    if any(imports.values()):
        total = sum(imports.values())
        for k, v in imports.items():
            pct = round((v / total) * 100) if total else 0
            imports_section_lines.append(f"- **{k}** — {v} ({pct}%)")
        imports_section = "\n".join(imports_section_lines) + "\n"
    else:
        imports_section = "No JS/TS imports sampled.\n"

    frameworks_line = ", ".join(sorted(frameworks)) if frameworks else "none detected"

    body = f"""# Patterns

## Summary
Conventions inferred from {sampled_count} sampled source files out of {total_count} total. Status: **seeded — refine as features land**.

## Tags
`naming`, `di`, `error-handling`, `tests`, `imports`

## Context
This file was generated by `#patterns-seed` on {today} so the Pattern Critic has enforceable rules on the first cycle. Treat each section as a starting point. `@scribe` refines it as new patterns emerge from approved cycles. Heuristics are best-effort — if a section is wrong, edit it directly (this is the only wiki file where Dev may edit during bootstrap).

**Detected frameworks / libraries:** {frameworks_line}

## Entries

### {today} — Initial seed

{format_section("File naming", file_naming, "No file naming pattern detected.")}

{format_section("Test file naming", test_naming, "No test files detected. Add test conventions here once tests exist.")}

### Import conventions

{imports_section}

{format_section("Dependency injection", di_style, "No DI pattern detected. Document manually when one emerges.")}

{format_section("Error handling", error_handling, "No clear error-handling pattern detected. Document manually.")}

## Last Updated
{today} — `#patterns-seed` initial run
"""
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PATTERNS.md from an existing codebase.")
    parser.add_argument("--root", default=".", help="Project root to scan (default: cwd)")
    parser.add_argument("--sample-size", type=int, default=30, help="Files to sample per language (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without touching disk")
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-empty PATTERNS.md")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wiki_dir = root / ".wiki"
    patterns_path = wiki_dir / "PATTERNS.md"

    if not wiki_dir.exists():
        print(f"[error] .wiki/ not found at {wiki_dir}. Run #wiki-init first.", file=sys.stderr)
        return 2

    if patterns_path.exists() and patterns_path.read_text(encoding="utf-8").strip() and not args.force:
        # Allow overwriting if file only contains the empty template
        content = patterns_path.read_text(encoding="utf-8")
        if "Entries" in content and content.count("###") > 1:
            print(f"[error] {patterns_path} already populated. Re-run with --force to overwrite.", file=sys.stderr)
            return 1

    all_files = find_source_files(root)
    source_files = [f for f in all_files if not any(p.match(f.name) for p, _ in TEST_FILE_PATTERNS)]
    test_files = [f for f in all_files if any(p.match(f.name) for p, _ in TEST_FILE_PATTERNS)]

    if not all_files:
        print("[error] no supported source files found.", file=sys.stderr)
        return 1

    # Sample
    by_lang: dict[str, list[Path]] = {}
    for f in source_files:
        lang = SUPPORTED_EXTS.get(f.suffix.lower())
        if lang:
            by_lang.setdefault(lang, []).append(f)

    sampled: list[Path] = []
    for lang_files in by_lang.values():
        sampled.extend(sample_files(lang_files, args.sample_size))

    file_naming = infer_file_naming(source_files)
    test_naming, _ = infer_test_conventions(test_files)
    imports = infer_imports(sampled)
    error_handling = infer_error_handling(sampled)
    di_style = infer_di_style(sampled)
    frameworks = detect_frameworks(root)

    md = build_patterns_md(
        root=root,
        file_naming=file_naming,
        test_naming=test_naming,
        imports=imports,
        error_handling=error_handling,
        di_style=di_style,
        frameworks=frameworks,
        sampled_count=len(sampled),
        total_count=len(all_files),
    )

    if args.dry_run:
        print(f"[dry-run] would write {patterns_path}")
        print("---")
        print(md)
        return 0

    patterns_path.write_text(md, encoding="utf-8")
    print(f"[ok] wrote {patterns_path} ({len(md)} bytes, sampled {len(sampled)}/{len(all_files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
