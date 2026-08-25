# MONOREPO — integrating the kit into a large workspace repo

For a TS/JS workspace monorepo (`packages/*`, `apps/*` + `libs/*`), roughly
30–100 packages. One install at the root — never per folder (one hook, one
CI, one manifest, one vocabulary; hierarchy lives in the CARDS). The core
anti-failure principle: **every phase is small, checkpointed, additive, and
independently abortable.** Nothing here touches source code; aborting at any
phase leaves the repo exactly as it was plus some markdown.

## Why size will not break it

- The scripts scale mechanically: validate/index/resolve read cards
  (markdown), not code — 300 cards parse in well under a second. Only
  kb-drift reads source, and Phase 1 times it before anything depends on it.
- **Partial coverage is legal by design.** Uncovered packages simply aren't
  resolvable yet; drift reports their files as INFO; agents behave normally
  there. You never need "the whole repo carded" for the covered slice to
  deliver full value.
- Every card batch passes `kb:validate` + your review before the next
  starts. A bad batch is deleted, not untangled.

## Phase 0 — choose the pilot slice (30 minutes, on paper)

Pick ONE domain you actively work in, plus the shared packages it imports
(ui-components, api-client, utils — the internal "contracts" everything
else flows through). Target: **15–25 module cards total**. Write the
package list down; it is the boundary for everything below. Do NOT plan
full coverage — the growth loop (Phase 7) cards the rest on touch.

## Phase 1 — mechanical install + scale check (½ day)

1. `./install.sh /path/to/monorepo <system> --with-pipeline`, then
   `git config core.hooksPath .githooks`.
2. **Solo/POC mode: delete (don't commit) `.github/workflows/knowledge-layer.yml`
   for now** — its blocking validate job would hit every teammate's PR.
   Your local hook + `kb:catchup` carry enforcement until the team opts in.
3. Edit `scripts/kb/kb.config.json`:
   `"srcDirs": ["packages", "apps", "libs"]` (the walker recurses and skips
   `node_modules` — plain top-level dirs are enough, no globs needed).
4. **Aliases — the one real monorepo gap, check it NOW:** cross-package
   imports by workspace name (`@acme/ui`) look like npm packages to
   kb-drift and would be skipped — silently missing exactly the
   cross-package edges you care about most.
   - If the repo uses `tsconfig.base.json` `paths` (most workspace/Nx
     setups do): mirror them, e.g. `"aliases": { "@acme/": "packages/" }`,
     and spot-check resolution in step 5.
   - If imports resolve only via each package's `package.json`
     `main`/`exports` (deep entry points, `src/index.ts` barrels): the
     resolver needs the small workspace extension (read the target
     package.json — ~30 lines in `kb-drift.mjs`). Flag it; don't proceed to
     Phase 5 trusting drift until resolution is confirmed.
5. **Timing + config dry-run before any card exists:** `npm run kb:drift`
   with zero cards parses the whole tree and prints
   `INFO N source file(s) owned by no card`. This proves the walker,
   config, and parse time at full scale on day one. If the full tree is
   slow (minutes), scope `srcDirs` to the pilot packages for now and note
   "full drift = nightly job" for later.

**Checkpoint:** drift dry-run runs clean and fast enough; alias resolution
confirmed on 2–3 known cross-package imports. Abort cost so far: zero.

## Phase 2 — vocabulary, two-level, pilot-scoped (½ day, human-owned)

Seed `docs/cards/_vocabulary.md` with: one **domain tag per domain**
(`checkout`, `catalog`, `platform-ui`, …— ~10–20, covers the WHOLE repo
cheaply) and **capability tags only for the pilot slice** (~15–25). Total
~30–45 tags now; other domains get capability tags when they get module
cards. Do not taxonomize the whole company in one sitting — that list will
be wrong and everything downstream inherits it.

## Phase 3 — instruction router (½–1 day)

Fill `.github/copilot-instructions.md` from repo evidence (commands incl.
the workspace runner — turbo/nx filters —, invariants, cross-cutting
triggers like codegen or versioning rules). Area instructions
(`applyTo: "packages/checkout/**"` etc.) for the PILOT packages only.
Router paragraph unchanged: resolve through cards, don't grep.

## Phase 4 — cards: full CLAIM coverage, pilot DETAIL coverage (1–2 days)

The move that makes guard/drift work repo-wide without carding everything:

1. **Thin domain cards for EVERY domain** (~10–15 lines each): id
   `<system>.<domain>`, owns its domain tag, `code:` claims the whole
   package group (`packages/checkout/`), prose = 2–3 sentences + the line
   "Not yet detailed — module cards exist only where listed in depends_on."
   Now every source file has an owner: guard nags work everywhere, drift
   has no unclaimed noise — for a page of markdown per domain.
2. **Module cards for the pilot slice + shared packages** — batches of ~5,
   shared packages FIRST (they are the seams), `/bootstrap-knowledge-layer`
   drives it with your review gates; fan out `@cartographer` one package
   per invocation for speed. Longest-claim-wins means a module card's
   claim (`packages/checkout/src/payments/`) simply out-scopes the domain
   card's — no restructuring when you detail a domain later.

**Checkpoint per batch:** `kb:validate` green + your review. Bad batch →
delete the files, nothing else moved.

## Phase 5 — wire the graph (½ day)

`kb:index` → commit manifest. `kb:drift` → declare the real edges it finds
(expect a wave the first time — that wave IS the map of your monorepo's
coupling; budget an hour to triage it). Spot-check `kb:resolve` on 3 tags —
sets should feel right to a human. Set the solo baseline:
`npm run kb:catchup -- --mark`. Commit everything (hook now enforces).

## Phase 6 — pipeline, pilot slice only (1 day incl. first real cycle)

The pipeline is installed repo-wide but USE it only inside the slice while
detail coverage is thin — the spec-critic will (correctly) reject work in
undetailed domains with "missing card coverage". Fill the cross-cutting
triggers section with the monorepo's real ones (codegen regeneration,
changeset/version bumps, build-graph implications). Note: the decomposition
trigger ">2 cards touched" fires more easily in a monorepo; if every small
change decomposes, raise the threshold in `semipilot-core.md` deliberately.
Run ONE real requirement end-to-end as the acceptance test.

## Phase 7 — the growth loop (steady state)

- **Card-on-touch:** first time real work enters an undetailed domain, the
  pipeline's "missing card coverage" blocker is the trigger — detail THAT
  domain (one bootstrap batch), then proceed. Coverage grows along the path
  of actual work, which is the only prioritization that never wastes effort.
- After every pull: `kb:catchup` (solo mode).
- Team adoption later: commit the CI workflow — with drift scoped per-PR to
  affected packages and the full graph as a nightly job if Phase 1 timing
  said so; add `CODEOWNERS` lines per `docs/cards/<domain>*` so each team
  reviews its own cards.

## Failure modes → recoveries

| Worry | Reality / recovery |
|---|---|
| "Bootstrap explodes on repo size" | It never runs repo-wide: batches of ~5 cards, review-gated; cartographer reads one package per invocation. Worst case a batch is bad → delete it. |
| Drift too slow on full tree | Known after the Phase 1 dry-run, before anything depends on it → scope srcDirs, nightly full run. |
| Drift misses cross-package edges | The alias check in Phase 1 step 4 exists precisely for this; don't trust drift until it passes. |
| First drift run reports 100+ edges | Normal — that's real coupling being mapped. Triage once; thereafter it's incremental. |
| Vocabulary wrong at scale | It's pilot-scoped and closed; wrong tags are renamed by PR while only ~20 cards use them. |
| Cards go stale outside the slice | Domain cards claim everything, so guard/catchup still nag; detail arrives on touch. |
| Teammates annoyed | Nothing you committed runs on their machines (hook is per-clone) and no CI is installed yet. |

**Total pilot budget: roughly 4–6 focused days** to a working layer +
pipeline in one domain — versus weeks for full coverage, which you should
refuse to attempt up front.
