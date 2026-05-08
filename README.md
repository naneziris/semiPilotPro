# SemiPilot Pro

An agentic software development system for GitHub Copilot in VS Code. It takes a raw idea through requirements, planning, implementation, and documentation — enforcing quality at two gated checkpoints and keeping the wiki as the team's shared memory.

---

## How it works

Every change follows the same pipeline:

```
User Idea
  │
  ▼  (or run /run-pipeline to chain everything automatically)
  │
  ▼
Refine Requirements       →  .github/requirements/requirements.md
  │
  ▼
Gate 1: @spec-critic      →  APPROVED or REJECTED (+ rejection-log.md)
  │ ← human approves spec
  ▼
Create Implementation Plan  →  .github/implementation-plan.md
  │
  ▼
Implement (YAML rail)     →  code + tests, 11 enforced steps
  │
  ▼
Gate 2: @pattern-critic   →  APPROVED or REJECTED (+ rejection-log.md)
  │ ← human approves diff
  ▼
MR Description (optional) →  structured PR description
  │
  ▼
Scribe                    →  updated .wiki/ + CHANGELOG
```

Two human decisions per successful cycle: approve the spec, approve the diff. Everything else runs automatically.

---

## Structure

```
semiPilotPro/
├── semipilot-core.md           # Full system contract — pipeline, YAML rail, golden rules
├── copilot-instructions.md     # Copilot workspace entry point (mirrors core)
├── agents/
│   ├── refiner.agent.md        # Turns raw ideas into testable requirements
│   ├── planner.agent.md        # Writes concrete implementation plans
│   ├── spec-critic.agent.md    # Gate 1 — pre-implementation feasibility check
│   ├── pattern-critic.agent.md # Gate 2 — post-implementation standards check
│   └── scribe.agent.md         # Updates .wiki/ and CHANGELOG
├── prompts/
│   ├── run-pipeline.prompt.md          # Chains all steps; pauses at gates
│   ├── refine-requirements.prompt.md   # Writes requirements.md
│   ├── create-implementation-plan.prompt.md
│   ├── implement-plan.prompt.md        # Executes the 11-step YAML rail
│   ├── create-mr-description.prompt.md # Generates structured PR description
│   └── explain-changes.prompt.md       # Answers "why was X changed?" with source citations
├── skills/
│   ├── wiki-init/      # Scaffolds .wiki/ on first use
│   ├── llm-wiki/       # Builds a context document from wiki + source for LLM queries
│   ├── code-analyzer/  # Cyclomatic complexity + file-level deltas, JSON output
│   └── project-map/    # Monorepo package + dependency map
└── wiki-templates/     # Starter templates for the 7 wiki files
```

---

## Getting started

**1. Install**

Copy this folder into your project's `.github/` directory (or point your Copilot workspace at it):

```
your-project/
└── .github/
    ├── copilot-instructions.md
    ├── agents/
    ├── prompts/
    └── skills/
```

**2. Bootstrap the wiki**

```
#wiki-init
```

This scaffolds `.wiki/` with seven template files. `OVERVIEW.md` and `DATA_MODELS.md` are auto-seeded from detected manifests and schemas.

**3. Populate the critical wiki files**

Before running any cycle, fill in at least:

- `.wiki/PATTERNS.md` — naming, DI, error-handling, and test conventions
- `.wiki/DEPENDENCIES.md` — current, deprecated, and banned libraries
- `.wiki/DATA_MODELS.md` — key schemas

Budget 30–60 minutes. The critics cannot function without it and will fail loudly if it is missing.

**4. Run your first cycle**

```
/run-pipeline
```

Or manually, step by step:

```
/refine-requirements → @spec-critic → /create-implementation-plan → /implement-plan → @pattern-critic → /create-mr-description → @scribe
```

---

## The YAML rail

`/implement-plan` follows 11 enforced steps in order. Hard-block means the implementer stops and posts the verbatim error — it does not skip ahead.

| Step | Hard block? |
|---|---|
| 1. read_plan | yes |
| 2. read_wiki_patterns | yes |
| 3. write_tests_first | yes |
| 4. write_code | yes |
| 5. lint | yes |
| 6. type_check | yes |
| 7. unit_tests | yes |
| 8. explain_test_changes | yes |
| 9. complexity_check | no (flags for Gate 2) |
| 10. wiki_pattern_check | yes |
| 11. submit_for_pattern_critic | yes |

Step 8 (`explain_test_changes`) requires a documented reason for every pre-existing test that was modified. The pattern critic verifies these reasons before approving.

---

## The wiki (`.wiki/`)

Seven files. Scribe is the only agent that writes to them.

| File | Purpose |
|---|---|
| `OVERVIEW.md` | Tech stack, project purpose, team conventions |
| `ARCH_DECISIONS.md` | Architecture Decision Records |
| `DATA_MODELS.md` | Schemas, key types, relationships |
| `PATTERNS.md` | Naming, DI, error-handling, and test standards |
| `DEPENDENCIES.md` | Current / deprecated / banned libraries |
| `API.md` | Public API signatures and contracts |
| `CHANGELOG.md` | User-facing: what changed and why |

---

## Agents

| Agent | Role | Model |
|---|---|---|
| `@refiner` | Requirements analysis and gap detection | Claude Opus 4.6 |
| `@planner` | Technical implementation plan | Claude Sonnet 4.6 |
| `@spec-critic` | Gate 1 — pre-implementation feasibility | Claude Opus 4.6 |
| `@pattern-critic` | Gate 2 — post-implementation standards | Claude Opus 4.6 |
| `@scribe` | Wiki and changelog updates | Claude Sonnet 4.6 |

Critics run on Opus — a wrong gate call is the most expensive error in the pipeline.

---

## Prompts

| Prompt | Purpose |
|---|---|
| `/run-pipeline` | Full pipeline in one command; pauses at both gates |
| `/refine-requirements` | Write `requirements.md` from a raw idea |
| `/create-implementation-plan` | Write `implementation-plan.md` from an approved spec |
| `/implement-plan` | Execute the YAML rail: tests first, then code |
| `/create-mr-description` | Generate a structured PR description after Gate 2 |
| `/explain-changes` | Answer "why was X changed?" with citations to plan and diff |

---

## Skills

| Skill | Purpose |
|---|---|
| `#wiki-init` | Scaffold `.wiki/` on first use |
| `#llm-wiki` | Build a context document for LLM queries (concat or FAISS) |
| `#code-analyzer` | Cyclomatic complexity + file-level deltas, JSON output |
| `#project-map` | Monorepo package and dependency map |

All skills support `--dry-run`.

---

## Further reading

- [`USER_GUIDE.md`](USER_GUIDE.md) — walkthrough of every flow, troubleshooting, composition patterns
- [`semipilot-core.md`](semipilot-core.md) — full system contract and golden rules
