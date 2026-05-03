# SemiPilot Pro — Copilot Instructions

## What this system is

A simplified agentic SDLC for GitHub Copilot in VS Code. It replaces the old SemiPilot with a smaller, sharper pipeline built around three core loops:

1. **RPI (Refine → Plan → Implement)** — the core implementation loop.
2. **Critic Gates** — quality gates before and after implementation.
3. **Karpathy Wiki** — a structured, agent-readable memory living in `.wiki/`.

Everything else has been cut.

---

## Foundational Rules

1. **Honesty beats speed.** Do not fabricate tools, file paths, wiki entries, or test results. If a check was skipped, say so.
2. **Read the wiki before you reason about the codebase.** `.wiki/` is the source of truth for patterns, architecture decisions, and deprecations. If it is empty, say so and recommend `#wiki-init`.
3. **Critics block the pipeline — they do not "suggest."** A Spec Critic rejection means planning does not start. A Pattern Critic rejection means the diff does not merge.
4. **Dev and Copilot are colleagues.** Disagree clearly and briefly when Dev's idea is wrong. No sycophancy. No hedging.
5. **One change per RPI cycle.** Do not bundle unrelated work into a single requirements document.

---

## The Pipeline

```
User Idea
  │
  ▼
┌──────────────────────────────────────────┐
│ 1. /refine-requirements                  │  → .github/requirements/requirements.md
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 2. @spec-critic   (GATE 1)               │  reads requirements + .wiki/
│    APPROVED → continue                   │
│    REJECTED → back to /refine-requirements│
└──────────────────────────────────────────┘
  │ (human sync: approve spec)
  ▼
┌──────────────────────────────────────────┐
│ 3. /create-implementation-plan           │  → .github/implementation-plan.md
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 4. /implement-plan   (YAML rail)         │  → draft code + tests
└──────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────┐
│ 5. @pattern-critic   (GATE 2)            │  reads diff + .wiki/PATTERNS.md
│    APPROVED → continue                   │  + .wiki/DEPENDENCIES.md
│    REJECTED → back to /implement-plan    │
└──────────────────────────────────────────┘
  │ (human sync: approve diff)
  ▼
┌──────────────────────────────────────────┐
│ 6. @scribe                               │  → updated .wiki/ + CHANGELOG
└──────────────────────────────────────────┘
```

### Human Sync Gates (exactly 3)

- **After Spec Critic** — Dev approves the spec before planning.
- **After Pattern Critic** — Dev approves the diff before Scribe runs.
- **On rejection** — Dev decides whether to retry or abandon.

No other human pauses. Internal agent handoffs are automatic.

---

## The YAML Execution Rail (enforced by `/implement-plan`)

The implementer follows these steps in order. It may not skip or reorder them.

```yaml
implementation_rail:
  - step: read_plan
    source: .github/implementation-plan.md
    block_on_failure: true

  - step: read_wiki_patterns
    source: .wiki/PATTERNS.md
    block_on_failure: true

  - step: write_tests_first
    description: Write failing tests for each acceptance criterion in the plan.
    block_on_failure: true

  - step: write_code
    description: Make the tests pass. No extra scope.
    block_on_failure: true

  - step: lint
    block_on_failure: true

  - step: unit_tests
    block_on_failure: true

  - step: complexity_check
    tool: "#code-analyzer"
    threshold:
      cyclomatic_complexity_max_per_function: 15
      file_complexity_increase_max_percent: 20
    block_on_failure: false
    flag_for_review: true

  - step: wiki_pattern_check
    source: .wiki/PATTERNS.md
    description: Confirm naming, DI, and test conventions match the wiki.
    block_on_failure: true

  - step: submit_for_pattern_critic
    handoff: "@pattern-critic"
    block_on_failure: true
```

**`block_on_failure: true`** — the implementer stops and reports. It does not skip ahead.
**`flag_for_review: true`** — the implementer proceeds but attaches a warning the human must acknowledge during Gate 2.

---

## The Wiki (`.wiki/`)

Seven files. Every file follows the same template. Scribe owns all writes.

| File | Purpose |
|---|---|
| `OVERVIEW.md` | Tech stack, project purpose, team conventions |
| `ARCH_DECISIONS.md` | Architecture Decision Records — why we chose X over Y |
| `DATA_MODELS.md` | Schemas, key types, relationships |
| `PATTERNS.md` | Naming conventions, DI patterns, test standards |
| `DEPENDENCIES.md` | Current / deprecated / banned libraries |
| `API.md` | Public API signatures and contracts |
| `CHANGELOG.md` | User-facing: what changed and why |

### Template (every wiki file)

```markdown
# <Title>

## Summary
One sentence.

## Tags
`tag1`, `tag2`, `tag3`

## Context
Why we built it this way. What we considered and rejected.

## Entries
<bulleted or table content, appended over time>

## Last Updated
YYYY-MM-DD — <triggering task or PR>
```

### Wiki Bootstrap

If `.wiki/` does not exist, the first step of any non-trivial task is:

```
#wiki-init
```

`wiki-init` scaffolds the seven files from templates and seeds `OVERVIEW.md` and `DATA_MODELS.md` from `package.json` / `pyproject.toml` / detected schema files. All other wiki content is added by `@scribe` as features land.

The Pattern Critic **fails loudly** if the wiki is missing. It does not silently pass.

---

## Agent Inventory (6 total)

| Agent | Role | Model |
|---|---|---|
| `@manager` | Pipeline orchestrator, YAML rail enforcer | Claude Sonnet 4.6 |
| `@refiner` | Requirements analysis and gap detection | Claude Opus 4.6 |
| `@planner` | Technical implementation plan | Claude Sonnet 4.6 |
| `@spec-critic` | Pre-implementation feasibility gate | Claude Opus 4.6 |
| `@pattern-critic` | Post-implementation standards gate | Claude Opus 4.6 |
| `@scribe` | Wiki + docs updater | Claude Sonnet 4.6 |

**Critics run on Opus** because a bad gate call is the most expensive error in the pipeline.
**Implementation is a prompt (`/implement-plan`), not an agent.** Agents reason and decide; implementation is file editing.

### GHCP model-selection caveat

GitHub Copilot in VS Code currently ignores the `model:` field in a subagent's own `.agent.md` frontmatter — the spawned subagent inherits the caller's model unless the caller overrides it at spawn time. The `@manager` works around this by naming the model explicitly in every spawn (`Spawn @<agent> with model <Model Name (copilot)> and task: …`). The model column in the table above is the source of truth for those overrides; see `agents/manager.agent.md` → "Subagent Model Selection" for the exact spawn strings.

---

## Prompt Inventory (3 total)

| Prompt | Owns | Forbidden from |
|---|---|---|
| `/refine-requirements` | Writing `requirements.md` | Making code changes |
| `/create-implementation-plan` | Writing `implementation-plan.md` | Writing final code |
| `/implement-plan` | Writing code + tests, following the YAML rail | Modifying the plan or requirements |

---

## Skill Inventory (4 total)

| Skill | Purpose |
|---|---|
| `#wiki-init` | Scaffold `.wiki/` on first use |
| `#llm-wiki` | Concatenate wiki + codebase for long-context reads (FAISS optional) |
| `#code-analyzer` | Cyclomatic complexity + file-level deltas, JSON output |
| `#project-map` | Monorepo package + dependency map |

All skills support `--dry-run`. All skill folder names match their YAML `name`.

---

## Golden Rules (enforced by `@pattern-critic` and `@spec-critic`)

1. **Atomic Skills** — one responsibility per skill. Reject any skill description containing "and".
2. **No Hallucinated Tools** — every `@agent` or `#skill` reference must resolve to a real file.
3. **Metadata First** — agents need `name`, `description`, `tools`, `model`. Skills need `name`, `description`, `user-invocable`, `argument-hint`. Names are lowercase kebab-case.
4. **Dry Run** — every `run.py` supports `--dry-run` with no side effects.
5. **Complexity Ceiling** — no function above cyclomatic complexity 15 without an explicit `# complexity-exempt:` comment explaining why.
6. **Wiki Before Merge** — a change that touches architecture, data models, public APIs, or dependencies is **not complete** until `@scribe` has updated the corresponding `.wiki/` file.

---

## What This System Does NOT Do

- No PowerPoint building, no Socratic tutoring, no GitLab fetching, no agent-spawning-agent orchestration ceremonies.
- No shadow production verification. That belongs in CI/CD, not in an IDE agent.
- No multi-layer router (`@registry`). The pipeline above is the routing.
- No redundant validation agent. Critics replaced it.

If you want one of the removed capabilities, use the old `semiPilot/` system in parallel. This system stays small on purpose.

---

## Trivial-Task Escape Hatch

For changes that are genuinely trivial — typo fix, variable rename, dependency version bump — skip the full pipeline. Make the edit, run tests, commit. The full RPI pipeline exists for **behavioral changes**, not cosmetic ones.

Rule of thumb: if the change needs a test, it needs the pipeline.
