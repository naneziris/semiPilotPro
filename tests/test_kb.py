"""The knowledge-layer tool (skills/semipilot-knowledge/scripts/kb.py) and `semipilot kb`."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from semipilot.cli import main
from semipilot.kbcmd import kb_init
from semipilot.skills_pack import kb_script

sys.dont_write_bytecode = True  # never leave __pycache__ inside the skill
sys.path.insert(0, str(kb_script().parent))
import kb  # noqa: E402

CARD = """---
id: app.{slug}
owns: [{tags}]
depends_on: [{deps}]
code:
  - {code}
---
{body}
"""


def make_layer(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    for d in ("docs/cards", "docs/deep", "src/billing", "src/core", "src/ui", "pkg/app"):
        (root / d).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "docs/cards/_vocabulary.md").write_text("# V\n\n- `billing` — money\n- `ui` — screens\n- `core` — shared\n- `py` — python app\n")
    (root / "docs/cards/billing.md").write_text(CARD.format(slug="billing", tags="billing", deps="app.core", code="src/billing/", body="Bills."))
    (root / "docs/cards/core.md").write_text(CARD.format(slug="core", tags="core", deps="", code="src/core/", body="Core."))
    (root / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="", code="src/ui/", body="UI."))
    (root / "docs/cards/app.md").write_text(CARD.format(slug="app", tags="py", deps="", code="pkg/", body="Py app."))
    (root / "src/billing/index.ts").write_text('import { x } from "../core/util";\n// import { y } from "../ui/old";\nexport * from "./inv";\n')
    (root / "src/billing/inv.ts").write_text("export const i = 1;\n")
    (root / "src/core/util.ts").write_text("export const x = 1;\n")
    (root / "src/ui/view.ts").write_text('const v = require("../core/util");\n')
    (root / "pkg/__init__.py").write_text("")
    (root / "pkg/app/__init__.py").write_text("")
    (root / "pkg/app/main.py").write_text("from pkg.app import helpers\nimport json\n")
    (root / "pkg/app/helpers.py").write_text("")
    (root / "scripts/kb").mkdir(parents=True)
    (root / "scripts/kb/kb.config.json").write_text(json.dumps({"srcDirs": ["src", "pkg"]}))
    return root


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        code = kb.main(["--root", str(root), *args], out=out)
    finally:
        sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def test_validate_ok_and_warnings(tmp_path):
    root = make_layer(tmp_path)
    code, out, err = run(root, "validate")
    assert code == 0 and "4 cards, 4 tags" in out


@pytest.mark.parametrize("mutate,expected", [
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="nope", deps="", code="src/ui/", body="x")), 'tag "nope" is not in _vocabulary.md'),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="billing", deps="", code="src/ui/", body="x")), "one owner per tag"),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="", code="src/gone/", body="x")), "code path does not exist"),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="app.nope", code="src/ui/", body="x")), "does not resolve"),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="", code="src/ui/", body="")), "prose body is empty"),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="uix", tags="ui", deps="", code="src/ui/", body="x")), 'filename must be "uix.md"'),
    (lambda r: (r / "docs/cards/ui.md").write_text("---\nid: app.ui\nowns: [ui]\nweird: 1\ncode: [src/ui/]\n---\nx\n"), 'unknown frontmatter key "weird"'),
    (lambda r: (r / "docs/cards/ui.md").write_text("---\nid: app.ui\nowns: ['ui']\ncode: [src/ui/]\n---\nx\n"), "use double quotes"),
    (lambda r: (r / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="", code="../outside", body="x")), "code path does not exist"),
])
def test_validate_errors(tmp_path, mutate, expected):
    root = make_layer(tmp_path)
    mutate(root)
    code, out, err = run(root, "validate")
    assert code == 1 and expected in err, err


def test_resolve_is_one_hop_both_ways_and_deterministic(tmp_path):
    root = make_layer(tmp_path)
    code, out, _ = run(root, "resolve", "--tags", "core")
    assert code == 0
    assert "# matched: app.core" in out and "# expanded (one hop): app.billing" in out  # reverse dependent
    code2, out2, _ = run(root, "resolve", "--tags", "core")
    assert out == out2
    code, out, _ = run(root, "resolve", "--tags", "billing", "--json")
    r = json.loads(out)
    assert r["cards"] == ["docs/cards/billing.md", "docs/cards/core.md"]


def test_resolve_unknown_tag_lists_valid_ones(tmp_path):
    root = make_layer(tmp_path)
    code, _, err = run(root, "resolve", "--tags", "zzz")
    assert code == 1 and "unknown tag(s): zzz" in err and "valid tags: billing, core, py, ui" in err


def test_index_and_check(tmp_path):
    root = make_layer(tmp_path)
    assert run(root, "index", "--check")[0] == 1
    assert run(root, "index")[0] == 0
    m = json.loads((root / "docs/cards/manifest.json").read_text())
    assert m["tags"]["billing"] == ["app.billing"] and ["app.billing", "app.core"] in m["edges"]
    assert run(root, "index", "--check")[0] == 0
    # a manifest written by the earlier Node tool differs only in `$generated` and is accepted
    m["$generated"] = "scripts/kb/kb-index.mjs — do not edit by hand"
    (root / "docs/cards/manifest.json").write_text(json.dumps(m, indent=2))
    assert run(root, "index", "--check")[0] == 0


def test_drift_finds_undeclared_ts_and_python_edges(tmp_path):
    root = make_layer(tmp_path)
    code, out, err = run(root, "drift", "--verbose")
    # ui → core via require() is undeclared; billing → core is declared; the commented-out import is ignored
    assert code == 1 and "DRIFT  undeclared dependency: app.ui -> app.core" in err
    assert "app.billing -> app.ui" not in err
    (root / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="app.core", code="src/ui/", body="UI."))
    (root / "pkg/app/main.py").write_text("from src_does_not_exist import x\nfrom pkg.app import helpers\n")
    code, out, err = run(root, "drift")
    assert code == 0 and "0 undeclared" in out


def test_drift_python_cross_card_import(tmp_path):
    root = make_layer(tmp_path)
    (root / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="app.core", code="src/ui/", body="UI."))
    (root / "src/core/tool.py").write_text("")
    (root / "pkg/app/main.py").write_text("from src.core import tool\n")
    code, out, err = run(root, "drift")
    assert code == 1 and "app.app -> app.core" in err


def test_guard_reports_code_changed_without_card(tmp_path):
    root = make_layer(tmp_path)
    code, out, _ = run(root, "guard", "--files", "src/ui/view.ts", "src/billing/inv.ts", "docs/cards/billing.md")
    assert code == 0 and "docs/cards/ui.md (app.ui)" in out and "billing.md (app.billing)" not in out


def test_catchup_baseline_flow(tmp_path):
    root = make_layer(tmp_path)
    g = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)  # noqa: E731
    g("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    assert "no baseline yet" in run(root, "catchup")[1]
    assert run(root, "catchup", "--mark")[0] == 0
    (root / "src/ui/view.ts").write_text("export const v = 2;\n")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "teammate change")
    code, out, _ = run(root, "catchup")
    assert code == 0 and "docs/cards/ui.md (app.ui)" in out


def test_kb_runs_as_a_standalone_script(tmp_path):
    """The skill ships kb.py on its own; it must run with nothing but python3."""
    root = make_layer(tmp_path)
    r = subprocess.run([sys.executable, "-I", str(kb_script()), "validate"], cwd=root / "src", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr  # finds the project root from a subfolder


# ---------------------------------------------------------------- semipilot kb init / passthrough
def mkrepo(tmp_path: Path, files: dict) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return repo


def test_kb_init_installs_and_never_overwrites_knowledge(tmp_path):
    repo = mkrepo(tmp_path, {"docs/decisions.md": "# ours\n"})
    report, notes = kb_init(repo, system="Shop App")
    written = {str(p.relative_to(repo)) for a, p in report if a == "write"}
    assert {"scripts/kb/kb.py", "scripts/kb/kb.config.json", ".githooks/pre-commit", ".github/workflows/knowledge-layer.yml",
            "docs/cards/_vocabulary.md", "docs/README.md", "docs/dependencies.md", "docs/CHANGELOG.md", "AGENTS.md"} <= written
    assert (repo / "docs/decisions.md").read_text() == "# ours\n"
    assert "shop-app.<slug>" in (repo / "docs/README.md").read_text()
    assert "semipilot:knowledge-router" in (repo / "AGENTS.md").read_text()
    assert (repo / ".githooks/pre-commit").stat().st_mode & 0o111
    wf = (repo / ".github/workflows/knowledge-layer.yml").read_text()
    assert "working-directory: ." in wf and "kb.py validate" in wf and "${{ github.base_ref }}" in wf
    assert any("core.hooksPath .githooks" in n for n in notes)
    before = (repo / "AGENTS.md").read_text()
    kb_init(repo)
    assert (repo / "AGENTS.md").read_text() == before  # router appended once


def test_kb_init_appends_router_to_existing_agents_md(tmp_path):
    repo = mkrepo(tmp_path, {"AGENTS.md": "# Mine\n\nRules.\n"})
    kb_init(repo)
    text = (repo / "AGENTS.md").read_text()
    assert text.startswith("# Mine\n\nRules.\n") and "kb.py resolve --tags" in text


def test_kb_init_in_a_monorepo_subfolder(tmp_path):
    repo = mkrepo(tmp_path, {"apps/api/README.md": "api\n"})
    api = repo / "apps/api"
    report, notes = kb_init(api)
    assert (api / "scripts/kb/kb.py").exists() and (api / ".githooks/pre-commit").exists()
    wf = repo / ".github/workflows/knowledge-layer-apps-api.yml"
    assert wf.exists() and "working-directory: apps/api" in wf.read_text()
    web = repo / "apps/web"
    web.mkdir()
    kb_init(web)  # a second project gets its own workflow, the first one's is untouched
    assert (repo / ".github/workflows/knowledge-layer-apps-web.yml").exists()
    assert "working-directory: apps/api" in wf.read_text()
    assert any("core.hooksPath apps/api/.githooks" in n for n in notes)


def test_kb_init_force_upgrades_a_node_install_but_keeps_cards(tmp_path):
    repo = mkrepo(tmp_path, {"scripts/kb/kb-validate.mjs": "x", ".githooks/pre-commit": "node scripts/kb/kb-validate.mjs\n",
                             "docs/cards/_vocabulary.md": "- `a`\n"})
    report, notes = kb_init(repo)
    assert "node" in (repo / ".githooks/pre-commit").read_text()  # not forced: kept
    assert any("kb-*.mjs" in n for n in notes)
    kb_init(repo, force=True)
    assert "kb.py validate" in (repo / ".githooks/pre-commit").read_text()
    assert (repo / "docs/cards/_vocabulary.md").read_text() == "- `a`\n"  # knowledge content never overwritten


def test_cli_kb_passthrough(tmp_path, monkeypatch, capsys):
    root = make_layer(tmp_path)
    monkeypatch.chdir(root / "src")
    assert main(["kb", "validate"]) == 0
    assert "4 cards" in capsys.readouterr().out
    assert main(["kb", "resolve", "--tags", "billing"]) == 0
    assert "docs/cards/core.md" in capsys.readouterr().out


def test_cli_kb_init(tmp_path, monkeypatch, capsys):
    repo = mkrepo(tmp_path, {})
    monkeypatch.chdir(repo)
    assert main(["kb", "init", "--system", "shop"]) == 0
    out = capsys.readouterr().out
    assert "installed  scripts/kb/kb.py" in out and "/semipilot-knowledge bootstrap" in out


def test_drift_ignores_imports_in_template_literals_and_trailing_comments(tmp_path):
    root = make_layer(tmp_path)
    (root / "docs/cards/ui.md").write_text(CARD.format(slug="ui", tags="ui", deps="app.core", code="src/ui/", body="UI."))
    (root / "src/billing/doc.ts").write_text('const s = `import { y } from "../ui/view"`;\nconst u = "http://x"; // import { z } from "../ui/view"\n')
    code, out, err = run(root, "drift")
    assert code == 0, err


def test_kb_init_warns_instead_of_replacing_another_hook_manager(tmp_path):
    repo = mkrepo(tmp_path, {})
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=repo, check=True)
    report, notes = kb_init(repo)
    assert any("already '.husky'" in n for n in notes) and not any(n.startswith("activate the hook") for n in notes)
