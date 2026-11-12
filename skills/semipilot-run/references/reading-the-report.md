# Reading `report.md`

`semipilot review <feature>` prints `.semipilot/features/<feature>/report.md`. Read it in this order — the order of
its sections is the order of risk.

## Section 0 — the review packet

Built so that the first ten minutes of the review go to the right places.

| Part | What it is | How to use it |
|---|---|---|
| **Risk tier, reviewer verdict, needs attention** | The tier the run had (and whether the plan's paths raised it), what the reviewer agent concluded, and anything mechanical that stands out: a blocker, failed final checks, blocked tasks, tests that passed before the code existed. | "Needs attention" is a list of facts, not a judgement. Start there. |
| **Read first** | Assumptions, the reviewer's blockers and majors, the places the reviewer says to open first, and the orchestrator's own signals (test-fixer edits, files outside the plan, retries). | Open each one in the code with the user. This list is the review's agenda. |
| **Evidence per acceptance criterion** | Criterion → its `[check:]` ref → the locked test file naming it → the task → status and commit → *Red first*. | *Red first: **no*** means the test passed with no implementation: read that test, it may prove nothing. *Test file: **none found*** means nothing checks that criterion. |
| **Where the change is** | Files by size of change, each with the task that planned it. | ***not in the plan*** = the implementer went outside its task (within tolerance). Read those. |
| **Reading order** | `git show <sha>` per task, in dependency order. | One commit at a time, then its test. |
| **Reviewer agent — rubric** | Eight items scored pass / concern / fail with evidence, then findings by severity. | Verify each finding in the code before acting on it. It points; it does not decide. A clean rubric is not a review. |

## Sections 1–11

| Section | What to look for | Typical action |
|---|---|---|
| **1. Assumptions** (`decisions.md`) | Every `D-<n>` entry is a choice the loop made where the spec was silent. Each lists the alternatives and how to undo it. | Wrong assumption → `semipilot rollback <feature> <task>`, add the answer to `requirements.md`, `semipilot resume <feature>`. |
| **2. Blocked tasks** | Why each task stopped: `BLOCKED: <question>` from the implementer (its changes were reverted), the same error twice (stuck), a diff over the cap, repeated scope violations. | Answer the question in `requirements.md` or `decisions.md`, then `resume`. Oversized → split the requirement. |
| **3. Completed tasks** | One commit per task. | Review the diff per commit (`git show <sha>`). |
| **3b. Pending** | Not attempted or interrupted (budget, outage, halt). | `resume` after fixing the cause. |
| **4. Check results** | The final full-suite run, or the last task's checks. A FAIL here after all tasks passed means tasks interfere. | Look at the warning in section 9; usually a new task or a spec fix. |
| **5. Diff stats** | Size per task. Large diffs deserve the closest review. | — |
| **6. Budget** | Agent calls used, wall-clock, and *Agent usage*: calls and minutes per role, plus what the CLI reports — dollars on Claude Code; premium requests and tokens on Copilot CLI (dollars once `cost.premium_request_usd` is set). | Raise `budget.*` only if the work was genuinely larger. A role that dominates the cost is where a cheaper model (`models.<role>`) pays. |
| **7. Infrastructure** | Harness, transient failures, outage minutes, whether the breaker tripped. | Repeated outages → run later; `infra.retry_window` can resume once automatically. |
| **8. Critic rejections** | What the plan critics rejected (also in `rejection-log.md`). | Recurring rejections → improve the instructions file or the cards. |
| **9. Warnings** | Locked-test edits that were reverted, out-of-scope files within tolerance, test-fixer contract edits (**review these**), tests already green before the code, refs no test names, tree resets. | A test-fixer edit must only change imports/names/signatures — check it. |
| **10–11** | Next steps and a PR description draft. | After the review: `semipilot mr <feature>` pushes the branch and opens a draft request with a description built from the packet. |

Files next to the report: `requirements.md`, `open-questions.md` (the answers), `implementation-plan.md` (tasks,
interfaces, *Knowledge Updates Required*), `plan.json`, `rejection-log.md`, `implementation-progress.json`
(checkpoint), and per-call logs in `.semipilot/runs/<run-id>/` (git-ignored; each log has the prompt, the agent's
answer, stdout, stderr and the classification).
