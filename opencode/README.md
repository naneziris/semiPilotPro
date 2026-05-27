# SemiPilot Pro — OpenCode Port

This folder contains the SemiPilot Pro pipeline adapted for [OpenCode](https://opencode.ai) (`sst/opencode`).

---

## What's here

```
opencode/
├── AGENTS.md          → project system prompt (equivalent to CLAUDE.md)
├── opencode.json      → default model config
├── agents/            → the 5 pipeline agents
│   ├── refiner.md
│   ├── spec-critic.md
│   ├── planner.md
│   ├── pattern-critic.md
│   └── scribe.md
└── commands/          → the 7 pipeline commands + 5 skill commands
    ├── run-pipeline.md
    ├── implement-plan.md
    ├── refine-requirements.md
    ├── create-implementation-plan.md
    ├── fix-rejection.md
    ├── write-tests.md
    ├── create-mr-description.md
    ├── explain-changes.md
    ├── wiki-init.md
    ├── patterns-seed.md
    ├── code-analyzer.md
    ├── project-map.md
    └── llm-wiki.md
```

---

## Deploying to a project

> **Critical:** OpenCode looks for agents and commands in **`.opencode/`** (with a leading dot). A folder named `opencode/` (no dot) will be silently ignored — agents and commands won't appear.

Run this from inside your target project directory:

```bash
# From inside your project root:

# System prompt — read automatically by OpenCode on every session
cp /path/to/semiPilotPro/opencode/AGENTS.md ./AGENTS.md

# Default model config
cp /path/to/semiPilotPro/opencode/opencode.json ./opencode.json

# Agents — note the leading dot in .opencode/
mkdir -p .opencode/agents
cp /path/to/semiPilotPro/opencode/agents/*.md .opencode/agents/

# Commands — note the leading dot in .opencode/
mkdir -p .opencode/commands
cp /path/to/semiPilotPro/opencode/commands/*.md .opencode/commands/
```

Verify the structure looks exactly like this:

```
your-project/
├── AGENTS.md               ← project root
├── opencode.json           ← project root
└── .opencode/              ← leading dot required
    ├── agents/
    │   ├── refiner.md
    │   ├── spec-critic.md
    │   ├── planner.md
    │   ├── pattern-critic.md
    │   └── scribe.md
    └── commands/
        ├── run-pipeline.md
        └── ...
```

After copying, restart OpenCode. Type `@` to see agents and `/` to see commands.

The skills (Python scripts in `skills/`) must also be accessible. Either:
- Keep the `semiPilotPro` repo alongside your project and update the paths in `opencode.json`, or
- Copy the `skills/` and `wiki-templates/` folders into the target project.

---

## Key differences from the Claude Code version

| Concern | Claude Code | OpenCode |
|---|---|---|
| System prompt | `CLAUDE.md` | `AGENTS.md` |
| Agent invocation | `Agent` tool with `subagent_type` | `@agent-name` inline |
| Commands | `.prompt.md` files (skills system) | `.opencode/commands/*.md` |
| Skill invocation | `#skill-name` | `/skill-name` |
| Config | `.claude/settings.json` | `opencode.json` |
| Context isolation | Each subagent runs in its own context window | Agents share the session context |

### Context management

In Claude Code, agents spawned via the `Agent` tool run in isolated context windows. In OpenCode, `@agent-name` delegation shares the session context. For long pipeline runs (especially `requirements-index` with multiple sub-cycles), consider using `/compact` between sub-cycles to keep context clean. OpenCode's built-in context window limits will also naturally trigger summarization.

---

## Prerequisites

- `ANTHROPIC_API_KEY` set in your environment
- OpenCode installed: `npm i -g opencode` (or see https://opencode.ai/docs/installation)
- Python 3.10+ (for skill scripts in `skills/`)

---

## First run in a new project

```
/wiki-init
/patterns-seed   # non-empty codebases only
/run-pipeline    # or start manually with /refine-requirements
```
