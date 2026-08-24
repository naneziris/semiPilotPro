# USAGE — the day-to-day flow of the agentic system

`INSTALL.md` covers adoption; this file covers what daily work looks like
AFTER a repo is set up, and what each part costs. (In an installed repo, the
same content lives as `INSTRUCTIONS.md` [pipeline flow] and `docs/README.md`
[knowledge-layer workflows] — this is the kit-level overview of both.)

---

**Both flows, solo/POC mode:** after every `git pull` of teammates' changes,
run `npm run kb:catchup` first (zero tokens — flags cards their changes made
stale; fix, `kb:index`, `kb:catchup -- --mark`). Details: `INSTALL.md > Solo
/ POC mode`.

## Flow A — knowledge layer only (no pipeline installed)

The layer makes ordinary Copilot chat/agent work dramatically better; you
drive the loop yourself:

1. **Start a task:** pick tags from `docs/cards/_vocabulary.md`, run
   `npm run kb:resolve -- --tags <t1,t2>`, read only what it returns — or
   just run `/impact` in Copilot chat, which does exactly that and produces
   an impact brief (touched cards, contracts at risk, invariants, open
   questions).
2. **Work** with Copilot as usual — the instruction files auto-load the
   conventions; the resolved cards are your context.
3. **After the change:** run `/sync-cards` — it diffs your work, finds stale
   cards/instructions, drafts the minimal edits, regenerates the manifest.
   New module → `/new-card`.
4. **Commit:** the pre-commit hook blocks broken/stale knowledge; CI
   re-checks and runs the drift analysis.

## Flow B — full pipeline (installed with `--with-pipeline`)

You are handed a requirement. Run `/run-pipeline` (or invoke the steps
manually) and interact at exactly these points:

```
you: /refine-requirements <the raw requirement>
 1. @refiner  — proposes tags        → YOU CONFIRM (one glance)
              — may ask ≤5 questions → YOU ANSWER
              → .github/requirements/requirements.md
 2. @spec-critic (GATE 1)            → YOU APPROVE the spec (or it kicks back)
 3. /create-implementation-plan      → .github/implementation-plan.md
 4. /implement-plan (11-step rail)   → code + tests
              — scope-expansion asks → YOU APPROVE/DECLINE if raised
 5. @pattern-critic (GATE 2)         → YOU APPROVE the diff
              — REJECTED → /fix-rejection loops back to 5
 6. @scribe   — updates cards/manifest/ADRs/changelog, verifies kb suite
 7. you: git commit                  → pre-commit hook = final backstop
```

Trivial change (typo, rename, version bump)? Skip the pipeline: edit, test,
commit — the hook still guards the knowledge layer. Rule of thumb: **if it
needs a test, it needs the pipeline.**

Escape hatches: start mid-pipeline or bypass a specific critic check by
declaring it in `.github/pipeline-overrides.yaml` — every bypass is logged
to `.github/rejection-log.md`, never silent.

## Standalone helpers (either flow)

`/write-tests` (tests for existing code, convention-enforced),
`/explain-changes` (why was this changed — cites plan + diff),
`/create-mr-description`, and in the kit itself
`bootstrap/generate-agents-md.prompt.md` (produce a self-contained AGENTS.md
for a repo you are NOT fully onboarding).

---

## What is scripted vs. what is AI — and what costs tokens

**Deterministic scripts — zero tokens, zero model involvement, same output
every run:**

| Thing | When it runs |
|---|---|
| `kb:validate` (card integrity), `kb:index`/`kb:check` (manifest), `kb:resolve` (retrieval), `kb:drift` (import graph vs cards), `kb:guard` (staleness nag), `kb:catchup` (solo/POC: which cards did teammates' pulled changes touch — personal baseline in `.git/`) | On demand, in the hook, and in CI |
| `.githooks/pre-commit` | Every commit |
| CI workflow (validate blocking, drift warning, guard nag) | Every PR/push |
| `install.sh` | Once per repo |
| `#code-analyzer` (`run.py` complexity check) | Rail step 9 + Gate 2 |

Note what this means: **retrieval itself is free.** Finding "which files
matter for this change" — normally the most token-hungry part of agentic
work (repo-wide grepping and file dumps) — is a script. The AI only ever
reads the small resolved set.

**AI — costs tokens, quality depends on the model:**

| Thing | Frequency | Relative cost |
|---|---|---|
| `/bootstrap-knowledge-layer` (+ `@cartographer`) | ONCE per repo | The big one-time spend: inventory + vocabulary + instructions + all cards. Budget accordingly; it is an investment that makes every later task cheaper |
| `@refiner`, `@planner`, `@scribe` | Per pipeline cycle | Small — each reads ~5–15 cards (~500 tokens each) + one artifact, never the codebase |
| `@implementer` | Per cycle | The bulk of a cycle's tokens (reads/writes real code, runs tests) — but isolated in its own context window; the orchestrator sees only a ~1–2 KB report |
| `@spec-critic` (Sonnet), `@pattern-critic` (Opus — the expensive gate) | Per cycle (+ per rejection retry) | `/gate-triage` (cheap, mechanical AI) pre-screens structurally broken artifacts so the expensive critic is never invoked on junk |
| `/impact`, `/sync-cards`, `/new-card`, `/write-tests` | On demand | Small — card-scoped context |

**The economics in one sentence:** you pay tokens once to BUILD the
knowledge (bootstrap) and a little per change to KEEP it true (scribe);
everything that must be trustworthy and repeatable — retrieval, validation,
freshness, enforcement — is a script and costs nothing. Ongoing maintenance
is deliberately weighted toward the free half: the hook and CI never
touch a model.
