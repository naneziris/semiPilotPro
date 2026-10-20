# The skill pack

semiPilot's interactive half is five skills in the open [Agent Skills](https://agentskills.io) format — a folder
with a `SKILL.md` (YAML frontmatter + instructions) and supporting `references/`, `examples/`, `scripts/` and
`assets/`. The same folders work in VS Code Copilot chat, Copilot CLI and Claude Code.

| Skill | Use it to | Invoke |
|---|---|---|
| [`semipilot-refine`](../skills/semipilot-refine/) | turn an idea into `requirements.md` with tagged acceptance criteria | `/semipilot-refine <idea>` |
| [`semipilot-spec-critic`](../skills/semipilot-spec-critic/) | Gate 1: review the spec; record your approval | `/semipilot-spec-critic [feature]`, then `approve` |
| [`semipilot-run`](../skills/semipilot-run/) | preflight, the planner's questions, status, report walk-through, rollback/resume | `/semipilot-run review <feature>` |
| [`semipilot-scribe`](../skills/semipilot-scribe/) | after review: update cards, ADRs, dependencies, changelog from the plan's list | `/semipilot-scribe <feature>` |
| [`semipilot-knowledge`](../skills/semipilot-knowledge/) | bootstrap and maintain the knowledge layer; impact analysis; AGENTS.md | `/semipilot-knowledge bootstrap` |

Every skill also triggers on its description, so "write requirements for…" or "update the cards for this change"
works without the slash command.

## How each harness finds them

`semipilot init` copies the pack into the project folder your chat reads:

| Chat | Project folder | Also reads | Invoke |
|---|---|---|---|
| VS Code Copilot chat | `.agents/skills/` | `.github/skills/`, `.claude/skills/` (Local harness) | `/semipilot-refine …` |
| Copilot CLI | `.agents/skills/` | `.github/skills/`, `.claude/skills/` | `/semipilot-refine …` |
| Claude Code | `.claude/skills/` | — | `/semipilot-refine …` |

`--skills both` installs into both folders. Copilot CLI then sees each skill twice (identical content) — harmless.
Commit the folders: the skills are part of how the team works on the repository, and reviewable like code.

Personal install instead (every repository, just you): copy `skills/semipilot-*` to `~/.claude/skills/` (Claude
Code) or `~/.copilot/skills/` / `~/.agents/skills/` (Copilot).

## Install as a plugin

The repository can also be installed as a plugin. One `.claude-plugin/` folder serves both harnesses (Claude Code
calls a plugin source a "marketplace"; here it is just this repository):

```bash
# Claude Code
claude plugin marketplace add naneziris/semiPilotPro
claude plugin install semipilot@semipilot          # skills appear as /semipilot:semipilot-refine …

# GitHub Copilot CLI
copilot plugin install naneziris/semiPilotPro
```

The plugin carries the skills only. The unattended loop is the `semipilot` CLI — install it separately
(`pipx install …`); `semipilot-run` checks for it and says how.

## Standalone use

`semipilot-refine`, `semipilot-spec-critic` and `semipilot-knowledge` are useful without the CLI: a tagged,
critic-reviewed spec improves any agent's work, and the knowledge layer's `kb.py` is a single standard-library Python
file. `semipilot-run` needs the CLI; `semipilot-scribe` needs a knowledge layer.

## Keeping the pack consistent

`tests/test_skills.py` checks every skill against the Agent Skills format on every test run: `name` lowercase-kebab
and equal to the folder, `description` written as a trigger ("Use when …", 50–1024 characters), `SKILL.md` under 500
lines, every relative link resolving inside the skill, text files only, no symlinks or OS junk, no secret-like
strings, `kb.py` standard-library only. When you change a skill's version, bump `metadata.version` in every
`SKILL.md`, `src/semipilot/__init__.py` and `.claude-plugin/*.json` together — a test fails if they disagree.

## Writing your own variant

Skills are plain Markdown. To change one for your team, copy it under a new name (e.g. `acme-refine`) rather than
editing the installed copy — `semipilot init` replaces `semipilot-*` folders from another version on every upgrade. To change what the
*unattended* roles do, override them in `.semipilot/roles/<role>.md` or `.semipilot/prompts/<name>.md`
([configuration.md](configuration.md#prompt-and-role-overrides)).
