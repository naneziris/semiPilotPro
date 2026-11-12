# Autonomy: risk tiers and the review gate

The loop can generate far more than a person can read. The limit on what it should do unattended is therefore not
what it can build but **what can be verified cheaply**: where a machine can prove "done", it may run alone; where
only a person can catch a wrong call, a person looks. 0.3 makes that a setting per feature instead of one setting
for everything, and spends machine time on making the human's review shorter.

## Risk tiers

Every requirements file names a tier in its frontmatter:

```markdown
---
feature: export-orders-csv
type: feat
risk: medium
status: approved
---
```

| Tier | What stops the run | What you do | Use it for |
|---|---|---|---|
| `low` | nothing | review the report at the end | mistakes the tests catch and a revert undoes |
| `medium` | once, after the critics accept the plan | read `implementation-plan.md`, then `semipilot approve <feature>` | design decisions that outlive the feature: a schema, an API shape, a new dependency between modules |
| `high` | the plan, and then every finished task | also read each commit, then `semipilot resume <feature>` | auth, money, migrations and deletion, public contracts — where a wrong call is expensive and tests would not show it |

`/semipilot-refine` proposes the tier from its impact analysis and says why; `/semipilot-spec-critic` rejects a
tier that is missing or lower than the analysis itself implies. Requirements without `risk:` get
`autonomy.default_risk` (`low`, the 0.2 behaviour); `autonomy.require_risk: true` makes preflight refuse them.

**The plan can raise the tier, never lower it.** A plan whose files match a pattern under `autonomy.escalate` runs
at least at that tier, whatever the requirements say — a "low" feature that turns out to edit the auth module is
not low. Out of the box, these paths mean at least `medium`:

```yaml
autonomy:
  escalate:
    medium: ["**/auth/**", "**/billing/**", "**/payments/**", "**/migrations/**", "**/*.sql",
             ".github/workflows/**", ".gitlab-ci.yml"]
    high: []
```

Replace the lists with your own sensitive paths (a list in your config replaces the default). The report says when
a tier was raised and by which files.

What a tier adds is itself configuration, so a team can, for example, review every task already at `medium`:

```yaml
autonomy:
  tiers:
    medium: {plan_approval: true, task_review: true}
```

Do not make everything `high`. A person asked to read every commit of a harmless change stops reading carefully,
and then the gate means nothing where it matters.

### The plan-approval stop

```
Your turn: the plan is ready and waits for your approval (this feature's risk tier asks for it)  [plan_approval]
Next:    read implementation-plan.md, then `semipilot approve calc`   (to change it: `semipilot replan calc -m "…"`)
```

Nothing has been built: no tests, no code. Reading a plan of a page or two is the cheapest review in the whole
process — you are reviewing the decisions before they become two thousand lines.

- `semipilot approve <feature>` records your approval (with a hash of the plan) and continues the run.
  `--no-run` only records it; `semipilot resume` continues later.
- `semipilot replan <feature> -m "use the existing OrderQuery, do not add a second query class"` drops the plan and
  plans again with your words in front of the planner, above the critics'. The new plan goes through the critics and
  stops for approval again. Your feedback is logged in `rejection-log.md`.
- An approval covers the plan it was given for. If the plan changes afterwards, the run stops for approval again.

### The per-task stop

```
Your turn: a task is done and waits for your review (this feature's risk tier asks for it)  [task_review]
  risk tier high: T2 is done — read `git show 4167ad88`, then `semipilot resume calc` (or `semipilot rollback calc T2`)
```

`resume` means "I read it, go on". `rollback` reverts the task (and anything built on it); fix the requirements,
then `resume` builds it again and stops again. The last task has no stop of its own — the end of the run is its
review.

Exit code 3 means "waiting for you" (questions, plan approval, task review); 2 is every other stop.

## Red before green

Locked tests are the loop's definition of done, so a test that cannot fail is a hole in the gate. Right after the
tests are locked — before any implementation exists — each task's tests are run and **must fail**. A task whose
tests already pass is flagged:

- in the report's review packet (*Red first: **no***) and under *Needs attention*;
- as a warning naming the test files, for you to read.

It usually means the test asserts nothing about the change, or the behaviour already exists. The same step flags
an acceptance ref that no locked test file names ("nothing checks those criteria").

```yaml
tests:
  red_check: warn      # warn | halt (stop the run: tests_not_red) | off
```

It needs a check whose command uses `{task_tests}`; without one it is skipped (`doctor` says so).

## The reviewer agent

After the last task, one read-only call (`reviewer` role) reads the whole diff and grades it against a rubric:
spec fidelity, test honesty, boundaries, simplicity, failure handling, security and data, readability, assumptions.
Each item is scored pass / concern / fail with evidence naming a file; findings are listed by severity; and it names
the three to six places a human should open first.

What it is, and is not:

- It is **advice to the reviewer**. It never blocks a run, never edits anything (read-only permission profile, and
  the tree is checked after the call), and a reviewer that cannot run — quota, outage — is a note in the report, not
  a failed run. `semipilot review <feature> --agent` runs it again.
- It is **not a second approval**. An agent grading an agent's work shares its blind spots. A blocker or a failed
  rubric item forces the verdict to *needs changes* whatever label the agent chose, but a clean rubric proves
  nothing: the report says so in the line under the table.
- The rubric is yours to change: copy `src/semipilot/roles/reviewer.md` to `.semipilot/roles/reviewer.md` and edit
  it — add the things your team's reviews actually catch.
- It costs one call per run. `models.reviewer` picks its model (a strong one pays here: it runs once and reads
  everything); `review.agent: false` turns it off.

## The review packet

`report.md` now opens with section 0, built so the first ten minutes of your review go to the right places:

| Part | Source |
|---|---|
| Risk tier, reviewer verdict, *Needs attention* | facts the orchestrator recorded: blockers, failed final checks, blocked tasks, tests green before the code |
| **Read first** | assumptions from `decisions.md`, the reviewer's blockers and majors, its read-first list, test-fixer edits, files outside the plan, retries |
| **Evidence per acceptance criterion** | criterion → `[check:]` ref → locked test file → task → status and commit → red first? |
| **Where the change is** | files by size of change, with the task that planned each (or ***not in the plan***) |
| **Reading order** | `git show <sha>` per task, in dependency order |
| **Reviewer agent — rubric** | the eight scores with evidence, then the findings |

The packet is built from what the orchestrator observed; the reviewer agent is one input among several. With the
reviewer off, everything but its own lines is still there.

`semipilot mr <feature>` turns the same material into the merge request's description — see [forge.md](forge.md).

## What this does not solve

The packet makes the review faster; it does not make it optional. If the branch is merged on the strength of a
green rubric, the code is unread, and the gap between what exists and what anybody understands grows with every
run — quietly, with the tests green. Risk tiers and the packet exist so that the reading you do is spent where it
matters, not so that you can stop.
