#!/usr/bin/env bash
# ai-ready-kit installer — copies the knowledge layer (and optionally the
# SemiPilot pipeline) into a target repository.
#
# Usage:
#   ./install.sh <target-repo-path> <system-name> [--with-pipeline]
#
#   <system-name>  lowercase-kebab prefix for card ids (e.g. "myapp" →
#                  cards get ids like myapp.billing)
#   --with-pipeline  also install the SemiPilot agents/prompts/skill
#
# The installer NEVER overwrites an existing file — it skips and reports, so
# it is safe to re-run. After installing, run the bootstrap (see the printed
# next steps and INSTALL.md).

set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
SYSTEM="${2:-}"
WITH_PIPELINE=false
[ "${3:-}" = "--with-pipeline" ] && WITH_PIPELINE=true

if [ -z "$TARGET" ] || [ -z "$SYSTEM" ]; then
  echo "usage: ./install.sh <target-repo-path> <system-name> [--with-pipeline]" >&2
  exit 1
fi
if [ ! -d "$TARGET" ]; then
  echo "error: target '$TARGET' is not a directory" >&2
  exit 1
fi
if ! echo "$SYSTEM" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
  echo "error: system-name must be lowercase kebab (got '$SYSTEM')" >&2
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"
REPO_NAME="$(basename "$TARGET")"

installed=0
skipped=0

# copy_file <src> <dest> [substitute]
copy_file() {
  local src="$1" dest="$2" sub="${3:-}"
  if [ -e "$dest" ]; then
    echo "  skip (exists): ${dest#"$TARGET"/}"
    skipped=$((skipped + 1))
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  if [ "$sub" = "substitute" ]; then
    sed -e "s/{{SYSTEM}}/$SYSTEM/g" -e "s/{{REPO_NAME}}/$REPO_NAME/g" "$src" > "$dest"
  else
    cp "$src" "$dest"
  fi
  chmod --reference="$src" "$dest" 2>/dev/null || chmod +x "$dest" 2>/dev/null || true
  echo "  installed:     ${dest#"$TARGET"/}"
  installed=$((installed + 1))
}

echo "== ai-ready-kit → $REPO_NAME (system: $SYSTEM) =="

echo "-- knowledge-layer scripts"
for f in "$KIT_DIR"/core/scripts/kb/*.mjs; do
  copy_file "$f" "$TARGET/scripts/kb/$(basename "$f")"
done
if [ ! -e "$TARGET/scripts/kb/kb.config.json" ]; then
  printf '{\n  "srcDirs": ["src"],\n  "aliases": { "@/": "src/" },\n  "extensions": [".ts", ".tsx"]\n}\n' \
    > "$TARGET/scripts/kb/kb.config.json"
  echo "  installed:     scripts/kb/kb.config.json (defaults — edit for your layout)"
  installed=$((installed + 1))
else
  echo "  skip (exists): scripts/kb/kb.config.json"; skipped=$((skipped + 1))
fi

echo "-- git hook, CI workflow, VS Code settings"
copy_file "$KIT_DIR/core/githooks/pre-commit" "$TARGET/.githooks/pre-commit"
chmod +x "$TARGET/.githooks/pre-commit" 2>/dev/null || true
copy_file "$KIT_DIR/core/workflows/knowledge-layer.yml" "$TARGET/.github/workflows/knowledge-layer.yml"
if [ -e "$TARGET/.vscode/settings.json" ]; then
  echo "  NOTE: .vscode/settings.json exists — merge in: \"chat.useAgentsMdFile\": true"
else
  copy_file "$KIT_DIR/core/vscode/settings.json" "$TARGET/.vscode/settings.json"
fi

echo "-- knowledge prompts"
for f in "$KIT_DIR"/core/prompts/*.md; do
  copy_file "$f" "$TARGET/.github/prompts/$(basename "$f")" substitute
done

echo "-- bootstrap prompt + cartographer agent"
copy_file "$KIT_DIR/bootstrap/bootstrap-knowledge-layer.prompt.md" \
  "$TARGET/.github/prompts/bootstrap-knowledge-layer.prompt.md" substitute
copy_file "$KIT_DIR/bootstrap/cartographer.agent.md" \
  "$TARGET/.github/agents/cartographer.agent.md" substitute

echo "-- knowledge docs (templates with {{TODO}} markers — the bootstrap fills them)"
copy_file "$KIT_DIR/templates/_vocabulary.template.md" "$TARGET/docs/cards/_vocabulary.md" substitute
copy_file "$KIT_DIR/templates/card.template.md" "$TARGET/docs/cards/_templates/card.template.md" substitute
copy_file "$KIT_DIR/templates/area.instructions.template.md" "$TARGET/docs/cards/_templates/area.instructions.template.md" substitute
copy_file "$KIT_DIR/templates/AGENTS-router-block.md" "$TARGET/docs/cards/_templates/AGENTS-router-block.md" substitute
copy_file "$KIT_DIR/templates/copilot-instructions.template.md" "$TARGET/.github/copilot-instructions.md" substitute
copy_file "$KIT_DIR/templates/docs-README.template.md" "$TARGET/docs/README.md" substitute
copy_file "$KIT_DIR/templates/decisions.template.md" "$TARGET/docs/decisions.md" substitute
copy_file "$KIT_DIR/templates/dependencies.template.md" "$TARGET/docs/dependencies.md" substitute
copy_file "$KIT_DIR/templates/CHANGELOG.template.md" "$TARGET/docs/CHANGELOG.md" substitute

echo "-- AGENTS.md router"
if [ -e "$TARGET/AGENTS.md" ]; then
  if grep -q "Repo knowledge router" "$TARGET/AGENTS.md"; then
    echo "  skip (router already present): AGENTS.md"
    skipped=$((skipped + 1))
  else
    echo "  NOTE: AGENTS.md exists — append docs/cards/_templates/AGENTS-router-block.md to it"
  fi
else
  copy_file "$KIT_DIR/templates/AGENTS-router-block.md" "$TARGET/AGENTS.md" substitute
fi

if $WITH_PIPELINE; then
  echo "-- SemiPilot pipeline (agents, prompts, skill, contract, manual)"
  for f in "$KIT_DIR"/pipeline/agents/*.md; do
    copy_file "$f" "$TARGET/.github/agents/$(basename "$f")" substitute
  done
  for f in "$KIT_DIR"/pipeline/prompts/*.md; do
    copy_file "$f" "$TARGET/.github/prompts/$(basename "$f")" substitute
  done
  copy_file "$KIT_DIR/pipeline/skills/code-analyzer/SKILL.md" "$TARGET/.github/skills/code-analyzer/SKILL.md"
  copy_file "$KIT_DIR/pipeline/skills/code-analyzer/run.py" "$TARGET/.github/skills/code-analyzer/run.py"
  chmod +x "$TARGET/.github/skills/code-analyzer/run.py" 2>/dev/null || true
  copy_file "$KIT_DIR/pipeline/semipilot-core.md" "$TARGET/semipilot-core.md" substitute
  copy_file "$KIT_DIR/pipeline/INSTRUCTIONS.template.md" "$TARGET/INSTRUCTIONS.md" substitute
fi

echo "-- package.json kb scripts"
if [ -e "$TARGET/package.json" ]; then
  node - "$TARGET/package.json" <<'EOF'
const fs = require("fs");
const file = process.argv[2];
const pkg = JSON.parse(fs.readFileSync(file, "utf8"));
pkg.scripts = pkg.scripts || {};
const wanted = {
  "kb:validate": "node scripts/kb/kb-validate.mjs",
  "kb:index": "node scripts/kb/kb-index.mjs",
  "kb:check": "node scripts/kb/kb-index.mjs --check",
  "kb:resolve": "node scripts/kb/kb-resolve.mjs",
  "kb:drift": "node scripts/kb/kb-drift.mjs",
  "kb:guard": "node scripts/kb/kb-guard.mjs",
  "kb:catchup": "node scripts/kb/kb-catchup.mjs",
};
let added = 0;
for (const [k, v] of Object.entries(wanted)) {
  if (!pkg.scripts[k]) { pkg.scripts[k] = v; added++; }
}
if (added > 0) fs.writeFileSync(file, JSON.stringify(pkg, null, 2) + "\n");
console.log(added > 0 ? `  added ${added} kb:* script(s) to package.json` : "  skip: kb:* scripts already present");
EOF
else
  echo "  NOTE: no package.json — invoke the scripts directly (node scripts/kb/kb-validate.mjs); the hook/CI/prompts assume 'npm run kb:*', adjust them"
fi

echo ""
echo "== done: $installed installed, $skipped skipped =="
cat <<EOF

NEXT STEPS (full guide: INSTALL.md in the kit):
 1. cd $TARGET && git config core.hooksPath .githooks
 2. Edit scripts/kb/kb.config.json if your source layout is not src/ + '@/' alias
    (non-TS repo? disable the drift job in .github/workflows/knowledge-layer.yml).
 3. Open the repo in VS Code and run: /bootstrap-knowledge-layer
    It inventories the repo, drafts the vocabulary and instructions for YOUR
    approval, then drafts cards seam-first for YOUR review, and iterates until
    npm run kb:validate && npm run kb:index && npm run kb:drift are green.
 4. Commit. The pre-commit hook and CI take it from there.
EOF
