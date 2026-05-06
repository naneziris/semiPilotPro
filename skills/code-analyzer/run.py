#!/usr/bin/env python3
"""Cyclomatic complexity analyzer for SemiPilot Pro.

Outputs JSON. Exit codes:
  0 — all functions under threshold
  1 — at least one function exceeds threshold
  2 — file unreadable or unsupported
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

SUPPORTED_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cs"}

BRANCH_TOKENS = [
    r"\bif\b",
    r"\belif\b",
    r"\belse\s+if\b",
    r"\bfor\b",
    r"\bwhile\b",
    r"\bcase\b",
    r"\bcatch\b",
    r"\bexcept\b",
    r"\band\b",
    r"\bor\b",
    r"&&",
    r"\|\|",
    r"\?(?!\s*[:.])",
]
BRANCH_RE = re.compile("|".join(BRANCH_TOKENS))

FUNCTION_PATTERNS = {
    ".py": re.compile(r"^\s*(async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),
    ".js": re.compile(r"(?:function\s+(\w+)\s*\(|(\w+)\s*[:=]\s*(?:async\s*)?\([^)]*\)\s*=>|(\w+)\s*\([^)]*\)\s*\{)", re.MULTILINE),
    ".ts": re.compile(r"(?:function\s+(\w+)\s*\(|(\w+)\s*[:=]\s*(?:async\s*)?\([^)]*\)\s*=>|(\w+)\s*\([^)]*\)\s*\{)", re.MULTILINE),
    ".go": re.compile(r"^func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(", re.MULTILINE),
    ".rs": re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[(<]", re.MULTILINE),
    ".java": re.compile(r"^\s*(?:public|private|protected|static|\s)+\s*[\w<>\[\],\s]+\s+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE),
}
FUNCTION_PATTERNS[".jsx"] = FUNCTION_PATTERNS[".js"]
FUNCTION_PATTERNS[".tsx"] = FUNCTION_PATTERNS[".ts"]
FUNCTION_PATTERNS[".cs"] = FUNCTION_PATTERNS[".java"]

EXEMPT_RE = re.compile(r"(?:#|//)\s*complexity-exempt:")


def find_function_blocks(content: str, ext: str) -> list:
    """Return [(name, start_line, end_line, body_text), ...].

    Heuristic: uses indentation for .py, brace-counting for others.
    """
    pattern = FUNCTION_PATTERNS.get(ext)
    if not pattern:
        return []

    lines = content.splitlines()
    results = []

    for match in pattern.finditer(content):
        name = next((g for g in match.groups() if g), "<anonymous>")
        # Anchor on the keyword position, not match.start(), because leading \s* can
        # consume the preceding newline and offset the line count by one.
        keyword_offsets = [content.find(kw, match.start(), match.end()) for kw in ("def ", "fn ", "func ", "function ")]
        anchors = [o for o in keyword_offsets if o >= 0]
        start_char = min(anchors) if anchors else match.start()
        start_line = content[:start_char].count("\n")

        if ext == ".py":
            header_line = lines[start_line]
            indent = len(header_line) - len(header_line.lstrip())
            end_line = len(lines)
            for i in range(start_line + 1, len(lines)):
                line = lines[i]
                if not line.strip():
                    continue
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= indent and line.strip():
                    end_line = i
                    break
            body = "\n".join(lines[start_line:end_line])
        else:
            brace_pos = content.find("{", start_char)
            if brace_pos == -1:
                continue
            depth = 0
            i = brace_pos
            while i < len(content):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            end_char = i
            end_line = content[:end_char].count("\n")
            body = content[start_char:end_char + 1]

        results.append((name, start_line + 1, end_line + 1, body))

    return results


def cyclomatic_complexity(body: str) -> int:
    """1 + count of branch tokens. Minimum 1 per function."""
    matches = BRANCH_RE.findall(body)
    return 1 + len(matches)


def is_exempt(body: str) -> bool:
    return bool(EXEMPT_RE.search(body))


def analyze(path: Path, threshold: int, baseline_total: Optional[int]) -> dict:
    ext = path.suffix
    if ext not in SUPPORTED_EXTS:
        return {"error": f"unsupported extension: {ext}", "file": str(path)}

    content = path.read_text(errors="replace")
    funcs = find_function_blocks(content, ext)

    function_reports = []
    file_total = 0
    violations = 0

    for name, start, end, body in funcs:
        cc = cyclomatic_complexity(body)
        file_total += cc
        exempt = is_exempt(body)
        over = cc > threshold and not exempt
        if over:
            violations += 1
        function_reports.append({
            "name": name,
            "lines": [start, end],
            "cyclomatic_complexity": cc,
            "exceeds_threshold": over,
            "exempt": exempt,
        })

    verdict = "pass" if violations == 0 else "fail"
    report = {
        "file": str(path),
        "threshold": threshold,
        "function_count": len(funcs),
        "file_cyclomatic_total": file_total,
        "violations": violations,
        "verdict": verdict,
        "functions": function_reports,
    }

    if baseline_total is not None and baseline_total > 0:
        delta_pct = ((file_total - baseline_total) / baseline_total) * 100
        report["baseline_total"] = baseline_total
        report["delta_percent"] = round(delta_pct, 1)
        report["delta_flag"] = delta_pct > 20

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Cyclomatic complexity analyzer.")
    parser.add_argument("file", help="Path to the file to analyze.")
    parser.add_argument("--threshold", type=int, default=15, help="Per-function CC threshold (default: 15).")
    parser.add_argument("--baseline", help="Path to baseline version of the file for delta comparison.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned action without reading file.")
    args = parser.parse_args()

    path = Path(args.file)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "file": str(path),
            "threshold": args.threshold,
            "baseline": args.baseline,
        }, indent=2))
        return 0

    if not path.exists():
        print(json.dumps({"error": f"file not found: {path}"}, indent=2))
        return 2

    baseline_total = None
    if args.baseline:
        bpath = Path(args.baseline)
        if bpath.exists():
            baseline_report = analyze(bpath, args.threshold, None)
            baseline_total = baseline_report.get("file_cyclomatic_total")

    report = analyze(path, args.threshold, baseline_total)
    print(json.dumps(report, indent=2))

    if "error" in report:
        return 2
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
