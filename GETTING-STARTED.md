# semiPilot — getting started

Two things to set up once per repository, in this order, then one flow per feature. The order matters only for one
file: both installers create `.github/copilot-instructions.md` if it is missing and never overwrite it, so install
the knowledge layer first and its router template is the one that stays. Nothing else overlaps.

## 1. Install the knowledge layer

The knowledge layer is what makes retrieval deterministic: one card per module, a closed tag vocabulary, and
scripts that validate and resolve them. It is optional — semipilot works without it — but every agent gets better
with it, and the critics can check the plan against real contracts instead of guesses.

```bash
git clone https://github.com/naneziris/semipilot-knowledge-layer
cd semipilot-knowledge-layer
./install.sh /path/to/your-repo <system-name>     # e.g. myapp → card ids like myapp.billing
cd /path/to/your-repo
git config core.hooksPath .githooks               # once per clone, every teammate
```

The installer only copies files (it never overwrites): `scripts/kb/`, the pre-commit hook, the CI workflow, the
knowledge prompts, and `{{TODO}}` templates for `.github/copilot-instructions.md`, `docs/cards/_vocabulary.md`,
`docs/decisions.md`, `docs/dependencies.md`, `docs/CHANGELOG.md`. Check `scripts/kb/kb.config.json` matches your
source layout (defaults: `src/`, `@/ → src/`, `.ts/.tsx`).

Then fill it — this is the real work, ½ to 2 days depending on the repo. Open the repo in VS Code and run
`/bootstrap-knowledge-layer` in Copilot chat. It inventories the repo, drafts the vocabulary and the instruction
files, then drafts cards seam-first, and stops for your approval at each gate. Do not skip the gates: an
unreviewed knowledge layer is deterministic misinformation. When `kb:validate`, `kb:index` and `kb:drift` are
green, commit. From then on cards change in the same PR as the code they describe — `@scribe` updates them after
each feature, the hook and CI enforce it.

Prerequisites: Node ≥ 20. Non-TypeScript repos: everything works except the import-drift check; disable that one
CI job.

## 2. Build a feature with semiPilot

Install the tool once (Python ≥ 3.9, git, the GitHub Copilot CLI logged in):

```bash
pipx install git+https://github.com/naneziris/semiPilotPro.git@v4
cd /path/to/your-repo
semipilot init          # detects your stack and the knowledge layer; installs /refine-requirements, /spec-critic and the agents
                        # (project in a subfolder of a monorepo? cd there and use `semipilot init --here`)
semipilot doctor        # confirm the checks in .semipilot/config.yaml and that Copilot answers
```

No pip or pipx on the machine? Download the `v4` branch as a ZIP instead, unzip it, and put its `bin/` folder on
your PATH — `bin/semipilot` (and `bin\semipilot.cmd` on Windows) runs it straight from the folder. Details in the
README under *Install*.

Then, for every new feature:

1. **Refine.** In VS Code Copilot chat: `/refine-requirements <your idea>`. `@refiner` confirms the tags with
   you, reads the resolved cards, asks at most five questions, and writes
   `.semipilot/features/<feature>/requirements.md`: problem, scope, impact analysis, acceptance criteria each
   tagged with the check that proves it, assumptions, open questions.
2. **Gate 1.** `/spec-critic`. `REJECTED` → run `/refine-requirements` again with the required fix. `APPROVED` →
   read the criteria one more time and reply **approve**. This is the last cheap point to fix a misread idea.
3. **Answer the planner.** In a terminal: `semipilot preflight <feature>`. It checks the requirements, the tree,
   the knowledge layer and Copilot, then writes the planner's questions to `open-questions.md`. Answer every
   question inline (copy the recommended default if it is right) and run `preflight` again until it says *Ready*.
4. **Run.** `semipilot run <feature>` on a machine that stays awake (`caffeinate -i …` on a Mac, or a dev
   container). PilotInLoop plans (`implementation-plan.md`), passes two critic gates, writes locked tests first,
   implements one task per fresh Copilot process, runs your checks after every attempt, and commits each passing
   task on its own branch (`feat/<feature>` by default, see `git.branch` in `.semipilot/config.yaml`) as a
   conventional commit (`feat(<feature>): <task>`), no bot marker — squash at merge time if that is your team's
   convention. It never pushes and never touches the knowledge layer. Takes minutes to hours depending on the
   feature; you do not need to watch it.
5. **Review.** `semipilot review <feature>`. Read the report in order: assumptions the loop made
   (`decisions.md`), blocked tasks and their question, completed tasks, check results, warnings. Wrong assumption
   → `semipilot rollback <feature> T<n>`, fix `requirements.md`, `semipilot resume <feature>`. Blocked or
   interrupted → answer in the requirements, `semipilot resume <feature>`.
6. **Close.** Review the diff, run `@scribe` in Copilot chat (it works from *Knowledge Updates Required* in
   `implementation-plan.md`: cards, instructions, ADR, changelog), commit, open the PR.

`semipilot status` shows where every feature stands. For a small, well-specified feature you can skip step 3 and
go straight to `run` — it performs the same checks and asks the same questions first.

### Rule of thumb

If it needs a test, it goes through the pipeline. Typos, renames and version bumps: edit, test, commit — the
pre-commit hook still guards the cards.
