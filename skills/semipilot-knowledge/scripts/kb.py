#!/usr/bin/env python3
"""kb — the knowledge-layer toolkit: validate, index, resolve, drift, guard, catchup.

One file, Python 3.9+ standard library only: it runs wherever `python3` runs, before any install step, in CI,
in a git hook, and inside any agent harness. `semipilot kb init` copies it to `scripts/kb/kb.py` in a repository;
it is also shipped inside the `semipilot-knowledge` skill.

The knowledge layer is a folder of module *cards* (`docs/cards/*.md`: strict YAML-subset frontmatter + a short
prose summary), a CLOSED tag vocabulary (`docs/cards/_vocabulary.md`) and a generated index
(`docs/cards/manifest.json`). Agents never grep for context: they pick tags, run `resolve`, and read exactly the
files it prints.

Usage (from anywhere inside the repository):
    python3 scripts/kb/kb.py validate                     cards well-formed, paths exist, edges resolve (exit 1 on error)
    python3 scripts/kb/kb.py index [--check]              (re)write docs/cards/manifest.json; --check fails if stale
    python3 scripts/kb/kb.py resolve --tags a,b           tags -> the exact reading list (cards, deep docs, code paths)
    python3 scripts/kb/kb.py drift [--verbose]            real import graph vs declared depends_on edges (exit 1 on drift)
    python3 scripts/kb/kb.py guard [--files f1 f2 ...]    which card-owned code changed without its card (never fails)
    python3 scripts/kb/kb.py catchup [--mark]             cards made stale by teammates since your last review
    python3 scripts/kb/kb.py --root <dir> <command>       operate on another project root

Exit codes: 0 ok · 1 validation error / drift / stale manifest · 2 usage error.

Security: reads files under the project root only; writes only docs/cards/manifest.json (`index`) and a
baseline marker inside .git/ (`catchup --mark`). No network access. Runs `git` read-only except that marker.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

VERSION = "2.0.0"
KB_CMD = "python3 scripts/kb/kb.py"

KNOWN_KEYS = ("id", "owns", "depends_on", "public_contracts", "code", "docs", "invariants")
LIST_KEYS = tuple(k for k in KNOWN_KEYS if k != "id")
MAX_CARD_LINES = 80
ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
TAG_RE = re.compile(r"^- `([a-z0-9-]+)`")


class KbError(Exception):
    """Fatal error with one or more messages (printed as ERROR lines, exit 1)."""

    def __init__(self, messages):
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("; ".join(self.messages))


# ============================================================================ project root
def find_root(start: Optional[Path] = None) -> Path:
    """The project root: nearest ancestor of `start` (default: cwd) holding docs/cards/_vocabulary.md; else the
    script's own repository (scripts/kb/kb.py -> two levels up); else the nearest git root; else cwd."""
    start = Path(start or os.getcwd()).resolve()
    for cand in (start, *start.parents):
        if (cand / "docs" / "cards" / "_vocabulary.md").exists():
            return cand
    here = Path(__file__).resolve()
    if here.parent.name == "kb" and here.parent.parent.name == "scripts":
        return here.parents[2]
    for cand in (start, *start.parents):
        if (cand / ".git").exists():
            return cand
    return start


@dataclass
class Paths:
    root: Path

    @property
    def cards(self) -> Path:
        return self.root / "docs" / "cards"

    @property
    def vocab(self) -> Path:
        return self.cards / "_vocabulary.md"

    @property
    def manifest(self) -> Path:
        return self.cards / "manifest.json"

    @property
    def config(self) -> Path:
        return self.root / "scripts" / "kb" / "kb.config.json"


# ============================================================================ parsing
def _unquote(raw: str, where: str) -> str:
    s = raw.strip()
    if s.startswith('"'):
        if not s.endswith('"') or len(s) < 2:
            raise ValueError(f"{where}: unterminated quoted string: {raw}")
        return s[1:-1]
    if s.startswith("'"):
        raise ValueError(f"{where}: use double quotes, not single: {raw}")
    return s


def parse_frontmatter(text: str, label: str) -> tuple[dict, str, list[str]]:
    """Parse the strict frontmatter subset. Returns (data, body, errors); errors are collected, not raised.

    Subset:  key: value  |  key: [a, b]  |  key:\\n  - item  (items/values optionally "double-quoted")."""
    errors: list[str] = []
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return {}, text, [f"{label}: no frontmatter (file must start with ---)"]
    data: dict = {}
    current: Optional[str] = None
    i = 1
    closed = False
    while i < len(lines):
        line = lines[i].rstrip("\r")
        if line == "---":
            closed = True
            break
        where = f"{label}:{i + 1}"
        i += 1
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"^ {2}- (.*)$", line)
        if item:
            if current is None:
                errors.append(f'{where}: list item without a preceding "key:" line')
                continue
            try:
                data[current].append(_unquote(item.group(1), where))
            except ValueError as e:
                errors.append(str(e))
            continue
        kv = re.match(r"^([A-Za-z0-9_]+):(.*)$", line)
        current = None
        if not kv:
            errors.append(f'{where}: unparseable line (subset is key: value, key: [..], "  - item"): {line}')
            continue
        key, rest = kv.group(1), kv.group(2).strip()
        if rest == "":
            data[key] = []
            current = key
        elif rest.startswith("["):
            if not rest.endswith("]"):
                errors.append(f"{where}: inline list must close on the same line")
                continue
            inner = rest[1:-1].strip()
            try:
                data[key] = [] if inner == "" else [_unquote(p, where) for p in inner.split(",")]
            except ValueError as e:
                errors.append(str(e))
        else:
            try:
                data[key] = _unquote(rest, where)
            except ValueError as e:
                errors.append(str(e))
    if not closed:
        errors.append(f"{label}: frontmatter never closed with ---")
    body = "\n".join(lines[i + 1:]).strip() if closed else ""
    return data, body, errors


@dataclass
class Card:
    file: str
    line_count: int
    id: str = ""
    owns: list = field(default_factory=list)
    depends_on: list = field(default_factory=list)
    public_contracts: list = field(default_factory=list)
    code: list = field(default_factory=list)
    docs: list = field(default_factory=list)
    invariants: list = field(default_factory=list)
    unknown_keys: list = field(default_factory=list)
    body: str = ""


def load_vocabulary(p: Paths) -> set[str]:
    if not p.vocab.exists():
        raise KbError(f"{p.vocab.relative_to(p.root)} not found — is this a knowledge-layer repository? (`semipilot kb init`)")
    tags = set()
    for line in p.vocab.read_text(encoding="utf-8").splitlines():
        m = TAG_RE.match(line)
        if m:
            tags.add(m.group(1))
    return tags


def load_cards(p: Paths) -> tuple[list[Card], list[str]]:
    cards: list[Card] = []
    errors: list[str] = []
    if not p.cards.is_dir():
        return cards, [f"{p.cards.relative_to(p.root)}/ not found"]
    for f in sorted(x for x in p.cards.iterdir() if x.suffix == ".md" and not x.name.startswith("_")):
        rel = f"docs/cards/{f.name}"
        text = f.read_text(encoding="utf-8")
        data, body, errs = parse_frontmatter(text, rel)
        errors += errs
        for key in LIST_KEYS:
            if key in data and not isinstance(data[key], list):
                errors.append(f'{rel}: "{key}" must be a list')
                data[key] = [data[key]]
        cards.append(Card(
            file=rel, line_count=len(text.split("\n")),
            id=data.get("id") if isinstance(data.get("id"), str) else "",
            owns=data.get("owns", []), depends_on=data.get("depends_on", []),
            public_contracts=data.get("public_contracts", []), code=data.get("code", []),
            docs=data.get("docs", []), invariants=data.get("invariants", []),
            unknown_keys=[k for k in data if k not in KNOWN_KEYS], body=body,
        ))
    return cards, errors


def normalize_claim(p: Paths, entry: str) -> Optional[str]:
    """A card's code:/docs: entry, normalized against the project: directories get a trailing '/'.
    None when the path does not exist or escapes the project root."""
    target = (p.root / entry).resolve()
    try:
        target.relative_to(p.root.resolve())
    except ValueError:
        return None
    if not target.exists():
        return None
    if target.is_dir() and not entry.endswith("/"):
        return entry + "/"
    return entry


def build_claims(p: Paths, cards: list[Card]) -> list[tuple[str, str]]:
    """(path, card id) ownership claims, longest first, so a card may own a subtree of another card's directory."""
    claims = [(normalize_claim(p, e) or e, c.id) for c in cards for e in c.code]
    claims.sort(key=lambda x: len(x[0]), reverse=True)
    return claims


def owner_of(rel: str, claims: list[tuple[str, str]]) -> Optional[str]:
    rel = rel.replace("\\", "/")
    for path, card in claims:
        if (rel.startswith(path) if path.endswith("/") else rel == path):
            return card
    return None


def stable_json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _rel(p: Paths, path: Path) -> str:
    return str(path.relative_to(p.root)).replace("\\", "/")


# ============================================================================ validate
def cmd_validate(p: Paths, out) -> int:
    vocabulary = load_vocabulary(p)
    cards, errors = load_cards(p)
    warnings: list[str] = []
    if not cards:
        errors.append("no cards found in docs/cards/")
    if not vocabulary:
        errors.append("no tags parsed from docs/cards/_vocabulary.md (format: - `tag` — meaning)")
    ids: dict[str, str] = {}
    tag_owner: dict[str, str] = {}
    claim_owner: dict[str, str] = {}
    for c in cards:
        w = c.file
        for k in c.unknown_keys:
            errors.append(f'{w}: unknown frontmatter key "{k}"')
        if not c.id:
            errors.append(f'{w}: missing required "id"')
        else:
            if not ID_RE.match(c.id):
                errors.append(f'{w}: id "{c.id}" must match <system>.<module> in lowercase kebab')
            if c.id in ids:
                errors.append(f'{w}: duplicate id "{c.id}" (also in {ids[c.id]})')
            ids[c.id] = w
            slug = c.id.split(".")[-1]
            if not w.endswith(f"/{slug}.md"):
                errors.append(f'{w}: filename must be "{slug}.md" to match id "{c.id}"')
        if not c.owns:
            errors.append(f'{w}: "owns" must list at least one tag')
        for t in c.owns:
            if t not in vocabulary:
                errors.append(f'{w}: tag "{t}" is not in _vocabulary.md (closed list — add it by PR first)')
            if t in tag_owner:
                errors.append(f'{w}: tag "{t}" already owned by {tag_owner[t]} — one owner per tag')
            tag_owner[t] = c.id or w
        if not c.code:
            errors.append(f'{w}: "code" must list at least one path')
        for e in c.code:
            n = normalize_claim(p, e)
            if n is None:
                errors.append(f"{w}: code path does not exist: {e}")
                continue
            if n in claim_owner:
                errors.append(f'{w}: code path "{n}" already claimed by {claim_owner[n]}')
            claim_owner[n] = c.id or w
        for e in c.docs:
            if normalize_claim(p, e) is None:
                errors.append(f"{w}: docs path does not exist: {e}")
        if not c.body:
            errors.append(f"{w}: prose body is empty — a card is a summary, not just metadata")
        if c.line_count > MAX_CARD_LINES:
            warnings.append(f"{w}: {c.line_count} lines (>{MAX_CARD_LINES}) — split the module or push detail to docs/deep/")
    for c in cards:
        for d in c.depends_on:
            if d == c.id:
                errors.append(f"{c.file}: depends_on contains itself")
            elif d not in ids:
                errors.append(f'{c.file}: depends_on "{d}" does not resolve to any card')
    for t in sorted(vocabulary):
        if t not in tag_owner:
            warnings.append(f'_vocabulary.md: tag "{t}" is owned by no card')
    for w in warnings:
        print(f"WARN   {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR  {e}", file=sys.stderr)
        print(f"\nkb validate: {len(errors)} error(s), {len(warnings)} warning(s), {len(cards)} card(s)", file=sys.stderr)
        return 1
    print(f"kb validate: OK — {len(cards)} cards, {len(vocabulary)} tags, {len(warnings)} warning(s)", file=out)
    return 0


# ============================================================================ index
def build_manifest(cards: list[Card]) -> dict:
    tags: dict[str, list] = {}
    index: dict[str, dict] = {}
    edges: list[list[str]] = []
    for c in cards:
        for t in c.owns:
            tags.setdefault(t, []).append(c.id)
        index[c.id] = {"file": c.file, "owns": sorted(c.owns), "code": sorted(c.code), "docs": sorted(c.docs),
                       "depends_on": sorted(c.depends_on)}
        edges += [[c.id, d] for d in c.depends_on]
    for v in tags.values():
        v.sort()
    edges.sort()
    return {"$generated": "scripts/kb/kb.py index — do not edit by hand", "cards": index, "edges": edges, "tags": tags}


def cmd_index(p: Paths, out, check: bool = False) -> int:
    cards, errors = load_cards(p)
    if errors:
        raise KbError(errors + ["fix parse errors (kb validate) before indexing"])
    text = stable_json(build_manifest(cards))
    if check:
        existing = p.manifest.read_text(encoding="utf-8") if p.manifest.exists() else ""
        if _same_manifest(existing, text):
            print("kb index: manifest up to date", file=out)
            return 0
        print(f"ERROR  docs/cards/manifest.json is stale — run `{KB_CMD} index` and commit the result", file=sys.stderr)
        return 1
    p.manifest.write_text(text, encoding="utf-8")
    edges = sum(len(c.depends_on) for c in cards)
    print(f"kb index: wrote docs/cards/manifest.json ({len(cards)} cards, {edges} edges)", file=out)
    return 0


def _same_manifest(existing: str, fresh: str) -> bool:
    """Compare content, not bytes: manifests written by the earlier Node version differ only in `$generated`."""
    try:
        a, b = json.loads(existing), json.loads(fresh)
    except ValueError:
        return False
    a.pop("$generated", None)
    b.pop("$generated", None)
    return a == b


# ============================================================================ resolve
def resolve(p: Paths, requested: list[str]) -> dict:
    """Deterministic retrieval: cards owning a requested tag, plus one hop along depends_on and reverse
    dependents, plus their deep docs; code paths last (read at execution time only)."""
    vocabulary = load_vocabulary(p)
    unknown = [t for t in requested if t not in vocabulary]
    if unknown:
        raise KbError([f"unknown tag(s): {', '.join(unknown)}", f"valid tags: {', '.join(sorted(vocabulary))}"])
    cards, errors = load_cards(p)
    if errors:
        raise KbError(errors + ["fix parse errors (kb validate) before resolving"])
    by_id = {c.id: c for c in cards}
    matched = {c.id for c in cards if any(t in requested for t in c.owns)}
    if not matched:
        raise KbError(f"no card owns any of: {', '.join(requested)}")
    expanded = set(matched)
    for cid in matched:
        expanded.update(by_id[cid].depends_on)
        expanded.update(c.id for c in cards if cid in c.depends_on)
    picked = [by_id[i] for i in sorted(expanded) if i in by_id]
    return {
        "tags": requested,
        "matched": sorted(matched),
        "expanded": sorted(expanded - matched),
        "cards": [c.file for c in picked],
        "docs": sorted({d for c in picked for d in c.docs}),
        "code": [(cp, c.id) for c in picked for cp in sorted(c.code)],
    }


def format_resolved(r: dict) -> str:
    L = [f"# kb resolve — tags: {', '.join(r['tags'])}", f"# matched: {', '.join(r['matched'])}",
         f"# expanded (one hop): {', '.join(r['expanded']) or '(none)'}", "", "## Read these cards (L1)"]
    L += r["cards"]
    L += ["", "## Deep docs if the card points you there (L2)"] + (r["docs"] or ["(none)"])
    L += ["", "## Code paths — execution time only (L3)"] + [f"{cp}  ({cid})" for cp, cid in r["code"]]
    return "\n".join(L)


def cmd_resolve(p: Paths, out, tags: Optional[str], as_json: bool = False) -> int:
    if not tags:
        print("usage: kb.py resolve --tags <tag1,tag2>  (tags come from docs/cards/_vocabulary.md)", file=sys.stderr)
        return 2
    requested = [t.strip() for t in tags.split(",") if t.strip()]
    r = resolve(p, requested)
    print(json.dumps(r, indent=2) if as_json else format_resolved(r), file=out)
    return 0


# ============================================================================ drift
DEFAULT_DRIFT = {"srcDirs": ["src"], "aliases": {"@/": "src/"},
                 "extensions": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".py"]}
_JS_IMPORT = re.compile(
    r"""(?:^|[\s;{}()])(?:import|export)\s+(?:type\s+)?(?:[\w*{}\s,$]+?\s+from\s+)?["']([^"'\n]+)["']"""
    r"""|\bimport\s*\(\s*["']([^"'\n]+)["']\s*\)"""
    r"""|\brequire\s*\(\s*["']([^"'\n]+)["']\s*\)""",
    re.MULTILINE,
)
_ASSET = re.compile(r"\.(css|scss|sass|less|svg|png|jpe?g|gif|webp|json|html)$")


def _strip_js_comments(text: str) -> str:
    """Remove block comments, line comments (also trailing ones; `://` in URLs is kept) and template literals, so
    import-looking text inside them is not taken for an import. Newlines are kept for line numbers."""
    keep_lines = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    text = re.sub(r"/\*.*?\*/", keep_lines, text, flags=re.DOTALL)
    text = re.sub(r"`(?:\\.|[^`\\])*`", keep_lines, text, flags=re.DOTALL)
    return re.sub(r"(?m)(^|[^:\\])//.*$", r"\1", text)


def js_specifiers(text: str) -> list[str]:
    """Static import / export-from / dynamic import() / require() specifiers. A deliberately simple extractor (no
    compiler needed): comments and template literals are ignored; an import-looking sequence inside an ordinary
    string literal can still be taken for an import and show up as DRIFT — declare or rephrase it."""
    return [a or b or c for a, b, c in _JS_IMPORT.findall(_strip_js_comments(text))]


def py_imports(text: str, rel: str) -> list[tuple[int, str, list[str]]]:
    """(level, module, names) for each import in a Python file; level > 0 for relative imports."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(0, a.name, []) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.level or 0, node.module or "", [a.name for a in node.names]))
    return out


class DriftAnalyzer:
    def __init__(self, p: Paths, cfg: dict):
        self.p = p
        self.cfg = cfg
        self.exts = tuple(cfg["extensions"])

    def source_files(self) -> list[Path]:
        files: list[Path] = []
        for d in self.cfg["srcDirs"]:
            base = self.p.root / d
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if any(part in ("node_modules", "__pycache__", ".venv", "venv", "dist", "build") for part in f.parts):
                    continue
                if f.is_file() and f.name.endswith(self.exts) and not f.name.endswith(".d.ts"):
                    files.append(f)
        return sorted(files)

    def _existing(self, base: Path, suffixes: list[str]) -> Optional[str]:
        for s in suffixes:
            cand = Path(str(base) + s)
            if cand.is_file():
                try:
                    return _rel(self.p, cand.resolve())
                except ValueError:
                    return None
        return None

    def resolve_js(self, spec: str, src: Path) -> Optional[str]:
        base = None
        for prefix, target in self.cfg["aliases"].items():
            if spec.startswith(prefix):
                base = self.p.root / target / spec[len(prefix):]
                break
        if base is None:
            if not spec.startswith("."):
                return None  # bare package import
            base = (src.parent / spec)
        js_exts = [e for e in self.exts if e != ".py"]
        hit = self._existing(base, ["", *js_exts, *[f"/index{e}" for e in js_exts]])
        return hit if hit else f"UNRESOLVED:{spec}"

    def resolve_py(self, level: int, module: str, names: list[str], src: Path) -> list[str]:
        if level:
            pkg = src.parent
            for _ in range(level - 1):
                pkg = pkg.parent
            roots = [pkg]
            parts = module.split(".") if module else []
        else:
            roots = [self.p.root] + [self.p.root / d for d in self.cfg["srcDirs"]]
            parts = module.split(".")
        hits = []
        for root in roots:
            mod = root.joinpath(*parts) if parts else root
            found = None
            for name in names:  # `from pkg import submodule`
                if name != "*":
                    found = self._existing(mod / name, [".py", "/__init__.py"]) or found
            found = found or self._existing(mod, [".py", "/__init__.py"])
            if found:
                hits.append(found)
                break
        return hits  # unresolved Python imports are treated as third-party

    def edges(self, claims) -> tuple[dict, set, list, int]:
        observed: dict[str, str] = {}
        unclaimed: set[str] = set()
        unresolved: list[str] = []
        files = self.source_files()
        for f in files:
            rel = _rel(self.p, f)
            frm = owner_of(rel, claims)
            if not frm:
                unclaimed.add(rel)
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            targets: list[str] = []
            if f.suffix == ".py":
                for level, module, names in py_imports(text, rel):
                    targets += self.resolve_py(level, module, names, f)
            else:
                for spec in js_specifiers(text):
                    t = self.resolve_js(spec, f)
                    if t is None:
                        continue
                    if t.startswith("UNRESOLVED:"):
                        if not _ASSET.search(spec):
                            unresolved.append(f"{rel}: {spec}")
                        continue
                    targets.append(t)
            for t in targets:
                to = owner_of(t, claims)
                if not to:
                    unclaimed.add(t)
                    continue
                if to != frm:
                    observed.setdefault(f"{frm} -> {to}", f"{rel} imports {t}")
        return observed, unclaimed, unresolved, len(files)


def load_drift_config(p: Paths) -> dict:
    cfg = dict(DEFAULT_DRIFT)
    if p.config.exists():
        try:
            cfg.update(json.loads(p.config.read_text(encoding="utf-8")))
        except ValueError as e:
            raise KbError(f"scripts/kb/kb.config.json is not valid JSON: {e}")
    return cfg


def cmd_drift(p: Paths, out, verbose: bool = False) -> int:
    cards, errors = load_cards(p)
    if errors:
        raise KbError(errors + ["fix parse errors (kb validate) before drift-checking"])
    claims = build_claims(p, cards)
    declared = {f"{c.id} -> {d}" for c in cards for d in c.depends_on}
    cfg = load_drift_config(p)
    analyzer = DriftAnalyzer(p, cfg)
    observed, unclaimed, unresolved, nfiles = analyzer.edges(claims)
    if nfiles == 0:
        raise KbError(f"no source files with {', '.join(cfg['extensions'])} under {', '.join(cfg['srcDirs'])} — "
                      "set srcDirs/extensions in scripts/kb/kb.config.json")
    drift = sorted(k for k in observed if k not in declared)
    unobserved = sorted(k for k in declared if k not in observed)
    if unclaimed:
        print(f"INFO   {len(unclaimed)} source file(s) owned by no card" + (":" if verbose else " (use --verbose to list)"), file=out)
        if verbose:
            for f in sorted(unclaimed):
                print(f"         {f}", file=out)
    for u in unresolved:
        print(f"INFO   unresolved import — {u}", file=out)
    for e in unobserved:
        print(f"INFO   declared but never imported (conceptual?): {e}", file=out)
    if drift:
        for e in drift:
            print(f"DRIFT  undeclared dependency: {e}   e.g. {observed[e]}", file=sys.stderr)
        print(f"\nkb drift: {len(drift)} undeclared edge(s). Declare them in the cards' depends_on or remove the import.",
              file=sys.stderr)
        return 1
    print(f"kb drift: OK — {nfiles} files, {len(observed)} card edges observed, 0 undeclared", file=out)
    return 0


# ============================================================================ guard / catchup
def stale_cards(p: Paths, changed: list[str]) -> tuple[list[tuple[Card, list[str]]], int]:
    cards, errors = load_cards(p)
    if errors:
        raise KbError(errors)
    claims = build_claims(p, cards)
    by_id = {c.id: c for c in cards}
    changed = [c.replace("\\", "/") for c in changed]
    card_files = {f for f in changed if f.startswith("docs/cards/")}
    touched: dict[str, list[str]] = {}
    for f in changed:
        o = owner_of(f, claims)
        if o:
            touched.setdefault(o, []).append(f)
    stale = [(by_id[cid], sorted(files)) for cid, files in touched.items() if by_id[cid].file not in card_files]
    return stale, len(touched)


def cmd_guard(p: Paths, out, files: Optional[list[str]]) -> int:
    changed = files if files else ([l.strip() for l in sys.stdin.read().splitlines() if l.strip()] if not sys.stdin.isatty() else [])
    if not changed:
        print("kb guard: no changed files supplied — nothing to check", file=out)
        return 0
    try:
        stale, ntouched = stale_cards(p, changed)
    except KbError:
        print("kb guard: card parse errors present — kb validate reports them", file=out)
        return 0  # the guard never fails a change on its own account
    if not stale:
        print(f"kb guard: OK — {ntouched} card area(s) touched, all cards updated or untouched code", file=out)
        return 0
    L = ["kb guard: these changes touch card-owned code without updating the card.",
         "If nothing the card says changed, ignore this; otherwise update the card in this change.", ""]
    for card, fs in stale:
        L.append(f"- {card.file} ({card.id}) — code touched:")
        L += [f"    {f}" for f in fs]
    report = "\n".join(L)
    print(report, file=out)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Knowledge-layer staleness check\n\n```\n{report}\n```\n")
    return 0


def _git(p: Paths, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=p.root, capture_output=True, text=True)
    if r.returncode != 0:
        raise KbError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def cmd_catchup(p: Paths, out, mark: bool = False) -> int:
    git_dir = (p.root / _git(p, "rev-parse", "--git-dir")).resolve()
    marker = git_dir / "kb-last-sync"
    head = _git(p, "rev-parse", "HEAD")
    if mark:
        marker.write_text(head + "\n", encoding="utf-8")
        print(f"kb catchup: baseline set to {head[:10]} — future reports cover changes after this commit", file=out)
        return 0
    if not marker.exists():
        print("kb catchup: no baseline yet.", file=out)
        print(f"Run `{KB_CMD} catchup --mark` at a point where the cards are true (e.g. now, after reviewing them).", file=out)
        return 0
    base = marker.read_text(encoding="utf-8").strip()
    try:
        _git(p, "cat-file", "-e", f"{base}^{{commit}}")
    except KbError:
        raise KbError(f"baseline {base[:10]} no longer exists (rebase/gc?) — run `{KB_CMD} catchup --mark` again")
    if base == head:
        print(f"kb catchup: baseline is HEAD ({head[:10]}) — nothing to catch up", file=out)
        return 0
    prefix = _git(p, "rev-parse", "--show-prefix")
    changed_all = [l for l in _git(p, "diff", "--name-only", f"{base}...{head}").splitlines() if l.strip()]
    changed = [c[len(prefix):] for c in changed_all if c.startswith(prefix)] if prefix else changed_all
    stale, _ = stale_cards(p, changed)
    print(f"kb catchup: {len(changed)} file(s) changed in {base[:10]}...{head[:10]}", file=out)
    if not stale:
        print("No card-owned code changed without its card. The knowledge layer looks current for this range.", file=out)
        print(f"Optional: `{KB_CMD} validate && {KB_CMD} drift`, then `{KB_CMD} catchup --mark`.", file=out)
        return 0
    print(f"\n{len(stale)} card(s) may be stale — their code changed without the card:\n", file=out)
    for card, fs in stale:
        print(f"- {card.file} ({card.id})", file=out)
        for f in fs:
            print(f"    {f}", file=out)
    print(f"""
Next (only the flagged cards, only this range):
 1. Skim the diff:      git diff {base[:10]}...HEAD -- <files above>
 2. Update the cards:   by hand, or ask your agent to "sync the knowledge cards" (semipilot-knowledge skill)
 3. Check:              {KB_CMD} validate && {KB_CMD} index && {KB_CMD} drift
 4. Move the baseline:  {KB_CMD} catchup --mark""", file=out)
    return 0


# ============================================================================ main
def main(argv: Optional[list[str]] = None, out=None) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="kb.py", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="project root (default: nearest ancestor of the current directory with docs/cards/_vocabulary.md)")
    ap.add_argument("--version", action="version", version=f"kb {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="cards well-formed, paths exist, edges resolve")
    s = sub.add_parser("index", help="write docs/cards/manifest.json")
    s.add_argument("--check", action="store_true", help="exit 1 if the committed manifest is stale")
    s = sub.add_parser("resolve", help="tags -> the exact reading list")
    s.add_argument("--tags", help="comma-separated tags from docs/cards/_vocabulary.md")
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s = sub.add_parser("drift", help="imports vs declared card edges")
    s.add_argument("--verbose", action="store_true")
    s = sub.add_parser("guard", help="card-owned code changed without its card (stdin or --files)")
    s.add_argument("--files", nargs="*")
    s = sub.add_parser("catchup", help="stale cards since your last review")
    s.add_argument("--mark", action="store_true", help="set the baseline to HEAD")
    a = ap.parse_args(argv)
    p = Paths(Path(a.root).resolve() if a.root else find_root())
    try:
        if a.cmd == "validate":
            return cmd_validate(p, out)
        if a.cmd == "index":
            return cmd_index(p, out, check=a.check)
        if a.cmd == "resolve":
            return cmd_resolve(p, out, a.tags, a.json)
        if a.cmd == "drift":
            return cmd_drift(p, out, a.verbose)
        if a.cmd == "guard":
            return cmd_guard(p, out, a.files)
        if a.cmd == "catchup":
            return cmd_catchup(p, out, a.mark)
    except KbError as e:
        for m in e.messages:
            print(f"ERROR  {m}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
