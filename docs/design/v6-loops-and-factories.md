# v6 (0.3) — design record: loops, harnesses and the review gate

2026-11-12. Why 0.3 looks the way it does. The starting point was an assessment of v5 (0.2) against three essays by
Addy Osmani — [The Factory Model](https://addyosmani.com/blog/factory-model/) (Feb 2026),
[Loop Engineering](https://addyosmani.com/blog/loop-engineering/) (Jun 2026) and
[Software Factories, Light and Dark](https://addyosmani.com/blog/software-factories/) (Jul 2026). This record keeps
the conclusions and the decisions, in our own words; read the essays for the argument.

## The ideas we measured against

1. **Loop → harness → factory.** A loop is one agent repeating gather / act / check until a condition holds. A
   harness is what surrounds it: sandbox, tools, memory that survives a run, the definition of done. A factory is
   many harnessed loops fed by a queue and drained through one review gate, with people owning it from above.
2. **Verification is the constraint, not generation.** A loop may be given only as much autonomy as can be checked
   cheaply and reliably. Everything in the pipeline scales except the human review gate.
3. **Dark versus lit.** A pipeline nobody reads accumulates code nobody understands, with the tests green the whole
   way. The fix is not one more review at the end but moving judgment upstream — to the spec, the design, the plan —
   and keeping the lights on wherever a wrong call is expensive. Deciding, per loop, which way the switch goes is
   the skilled part; setting every switch the same way is the failure.
4. **What earns a loop the dark:** a check that is cheap, runs every time, cannot easily be faked and answers at
   once; and a loop short enough to verify.
5. **Own the control flow.** Reliable agent systems are mostly deterministic code with model calls at chosen
   points — a graph with explicit steps and edges, not a model choosing its own path.
6. **Maker and checker are different agents**, and tests come first, red before green, because an agent optimising
   for passing tests will find a way to pass them.
7. **State lives on disk; knowledge is written down once** (skills), so each run does not re-derive the project.
8. **Watch the cost**, and do not surrender the thinking: the same loop makes one person faster and lets another
   stop understanding their own system.

## Where v5 already agreed

| Idea | v5 |
|---|---|
| Own the control flow | The orchestrator is a state machine in Python; an agent only acts inside one step and never decides that work is done. |
| Back pressure | Locked tests, the project's checks after every attempt, scope and diff caps, stuck detection, a full suite at the end. |
| Judgment upstream | Refiner, Gate 1 with a human approval, the planner's questions answered before anything is built. |
| Maker ≠ checker | Two critics on the plan; a fresh process per call; the implementer never sees the plan. |
| Tests first | A test-writer before any implementer; tests locked by checksum. |
| State on disk, knowledge written down | `implementation-progress.json`, `decisions.md`, `rejection-log.md`; the knowledge layer; Agent Skills. |
| Short loops | One task per fresh process, ≤ 5 files, ≤ 400 changed lines. |

## Where v5 disagreed, and what 0.3 does about it

| Gap in v5 | Why it matters | 0.3 |
|---|---|---|
| **One autonomy level for every feature.** A copy change and an auth change ran identically. | The essays' central warning: all switches set the same way. | Risk tiers per feature, raised by the plan's paths (`risk.py`); `plan_approval` and `task_review` gates. |
| **No human on the plan.** Architecture decisions were approved only by agents. | The cheapest review is of a decision before it is built. | `semipilot approve` / `replan` at medium and high risk. Left off at low risk on purpose: a gate nobody needs gets rubber-stamped. |
| **The review was deferred, not reduced.** One whole feature diff at the end. | The only box in the pipeline that does not scale got no help at all. | The review packet (what to read first, evidence per criterion, where the change is, reading order) and a rubric-based reviewer agent whose output feeds it. |
| **Tests were never checked for red.** | A test that passes before the code exists proves nothing, and locked tests are the definition of done. | The red check after the lock; refs that no test names are flagged. |
| **Cost blindness on Copilot.** | Loops multiply token use; you cannot manage what the report does not show. | A usage ledger per role on both harnesses, Copilot usage read from its session files or stats block, spend caps. |
| **Nothing small enough to run alone.** | Some loops do earn the dark, and v5 had no place for them. | `semipilot chore`: one fix, one mechanical gate, no human before the commit. |
| **No intake, no hand-off.** The loop began at a chat and ended at a local branch. | The queue and the review gate of the factory are outside the repository. | `semipilot intake`, `semipilot mr`. |

## Decisions and their reasons

- **Tiers are declared, then only raised.** A person (with the refiner) names the tier; Gate 1 checks it against the
  impact analysis; the plan's paths can push it up. Nothing can lower it during a run. An agent that could argue its
  own tier down would be grading its own homework.
- **Default escalation goes to `medium`, not `high`.** The default path list will have false positives
  (`components/auth/LoginButton.tsx`). Reading a plan costs a few minutes; reading every commit of a button change
  teaches people to stop reading. `high` is for paths a team names itself.
- **`default_risk` stays `low`.** Existing requirements keep working, and a default of `medium` would train people to
  approve plans by reflex — the lit factory where nobody can keep up is also a failure.
- **The reviewer is advice, never a gate.** A second agent catches what the first talked itself into, but it shares
  the model's blind spots, and a gate that an agent can pass is a dark gate with a light painted on it. So: read-only,
  cannot fail a run, a blocker forces *needs changes*, and the report says in plain words that it points and does
  not decide.
- **The packet is built from facts, not from the reviewer.** Evidence per criterion, the change map and the reading
  order come from what the orchestrator recorded. With the reviewer switched off the packet is still there.
- **Chores have no critics.** Their safety comes from being small and mechanically checked: a clean base, locked
  tests, size caps, the checks, and a finder that must report strictly fewer findings. Adding agents to a chore
  would make it slower and no safer. The moment a chore needs judgment it is a feature.
- **Chores obey back pressure.** A finding fixed on an unmerged branch is not fixed again, and at `max_open`
  waiting branches nothing new is attempted. Otherwise a scheduler turns a helpful loop into a queue of unread
  branches.
- **Only the program pushes, only when asked.** `git push` stays denied to every agent. `semipilot mr` is an explicit
  human command; the two `open_mr` settings are explicit opt-ins. Requests are drafts by default: opening one is not
  approving it.
- **An issue is untrusted input.** `intake` saves it as data under a notice; the refine skill is told to treat it as
  a description. The real protection is unchanged: a human approves the requirements at Gate 1.
- **Forge access through `gh` / `glab`, not an MCP server.** The orchestrator is deterministic Python and should not
  need a model to open a request; the CLIs are already installed and logged in where this is used, and no token
  passes through semiPilot. The refine skill may still use an issue tool in chat.
- **Usage is read, not requested.** Copilot's session files are read after the call; nothing about the call
  changes, so a wrong guess about the format costs a missing number, never a broken run. The alternative
  (`silent: false`) changes what the CLI prints and is therefore opt-in.

## Deliberately not built

- **Parallel runs and worktrees.** The essays present fleets of agents as the factory, and are equally clear that
  review bandwidth is the ceiling on how many you can run. With one reviewer, a second concurrent feature run only
  lengthens the queue at the gate. Revisit when one loop demonstrably saves more time than its review costs.
- **Scheduled feature runs / a queue of features.** A feature starts with a person refining requirements; there is
  nothing to schedule. Chores are the schedulable loop, and `semipilot chore` is one run that any scheduler can
  call — no scheduler of our own to maintain.
- **Production signals back into the queue** (the "maintain" stage). Useful once the loop has proven itself on
  features; out of scope before that.
- **Cross-harness critics** (build on one CLI, critique on the other). A real second opinion and both harnesses are
  already supported, but it doubles the moving parts of every run. Deferred by decision, not rejected.
- **A comprehension check on the human** (quizzes, mandatory sign-offs per file). Tempting against rubber-stamping,
  and exactly the ceremony people route around. The packet makes reading cheaper instead.

## What remains true

The loop is only as good as the checks and the reading around it. Risk tiers decide *where* a person looks and the
packet makes looking faster; neither makes it unnecessary. If the branches are merged unread, 0.3 is a dark factory
with better paperwork.

## Not verified at the time of writing

- Copilot usage readers against a live Copilot CLI (session-file layout, stats-block wording).
- `gh` / `glab` command lines against a live forge.
- The reviewer rubric's hit rate on real diffs — expect to tune `roles/reviewer.md` after the first runs.
