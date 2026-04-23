# SemiPilot Pro

A simplified agentic SDLC for GitHub Copilot in VS Code. Replaces the legacy `semiPilot/` system with a tighter RPI + Critics + Scribe pipeline built around the Karpathy Wiki pattern.

## What's in here

```
semiPilotPro/
├── copilot-instructions.md     # Ground truth — the pipeline, YAML rail, golden rules
├── agents/                     # 6 agents (was 9)
│   ├── manager.agent.md
│   ├── refiner.agent.md
│   ├── planner.agent.md
│   ├── spec-critic.agent.md    # NEW — Gate 1
│   ├── pattern-critic.agent.md # NEW — Gate 2
│   └── scribe.agent.md         # NEW — wiki & docs updater
├── prompts/                    # 3 prompts (was 6)
│   ├── refine-requirements.prompt.md
│   ├── create-implementation-plan.prompt.md
│   └── implement-plan.prompt.md
├── skills/                     # 4 skills (was 7)
│   ├── wiki-init/              # NEW — scaffold the .wiki/
│   ├── llm-wiki/               # concat default, FAISS optional
│   ├── code-analyzer/          # real cyclomatic complexity + thresholds
│   └── project-map/
└── wiki-templates/             # Standalone copies of the 7 wiki files
```

## What was cut

- `registry` agent (Manager handles routing now)
- `discovery` agent (absorbed into planner + spec-critic)
- `architect` agent (merged into planner)
- `validator` agent (replaced by critics)
- `llm-wiki` agent (just use the skill)
- `presentation-interviewer` agent
- `pattern-finder` skill (was a grep wrapper)
- `gitlab-fetcher` skill (wrong ecosystem for GH Copilot)
- `pptx-builder` + `style-extractor` skills (out of scope)
- `code-review`, `new-agent`, `socratic-tutor` prompts

The legacy system remains intact in `../` if you need any of the removed pieces.

## Pipeline at a glance

```
User Idea
  → /refine-requirements      (writes requirements.md)
  → @spec-critic               (GATE 1 — binary APPROVED/REJECTED)
      ↕ human sync
  → /create-implementation-plan (writes implementation-plan.md)
  → /implement-plan             (follows YAML rail; tests-first)
  → @pattern-critic             (GATE 2 — checks diff vs .wiki/)
      ↕ human sync
  → @scribe                    (updates .wiki/ + CHANGELOG)
```

Exactly 3 human sync points. No ceremonial pauses between internal handoffs.

## Getting started

1. Copy this folder into your project's `.github/` (or configure your Copilot workspace to point here).
2. Bootstrap the wiki: `#wiki-init`
3. Fill in `.wiki/OVERVIEW.md`, `.wiki/PATTERNS.md`, `.wiki/DATA_MODELS.md`, `.wiki/DEPENDENCIES.md` by hand. This is a one-time cost — the critics cannot function without it.
4. Kick off a real task with `@manager` or start directly with `/refine-requirements`.

## Design principles

1. **Critics block, they don't suggest.** Gate rejections stop the pipeline.
2. **The wiki is the memory.** Agents don't re-derive architecture from code every time.
3. **Tests are written first.** The YAML rail enforces TDD.
4. **Implementation is a prompt, not an agent.** Agents reason; prompts execute.
5. **Dry-run everywhere.** Every skill supports `--dry-run` with no side effects.

See `copilot-instructions.md` for the full contract.
