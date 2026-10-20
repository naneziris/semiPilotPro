# Reading `report.md`

`semipilot review <feature>` prints `.semipilot/features/<feature>/report.md`. Read it in this order — the order of
its sections is the order of risk.

| Section | What to look for | Typical action |
|---|---|---|
| **1. Assumptions** (`decisions.md`) | Every `D-<n>` entry is a choice the loop made where the spec was silent. Each lists the alternatives and how to undo it. | Wrong assumption → `semipilot rollback <feature> <task>`, add the answer to `requirements.md`, `semipilot resume <feature>`. |
| **2. Blocked tasks** | Why each task stopped: `BLOCKED: <question>` from the implementer (its changes were reverted), the same error twice (stuck), a diff over the cap, repeated scope violations. | Answer the question in `requirements.md` or `decisions.md`, then `resume`. Oversized → split the requirement. |
| **3. Completed tasks** | One commit per task. | Review the diff per commit (`git show <sha>`). |
| **3b. Pending** | Not attempted or interrupted (budget, outage, halt). | `resume` after fixing the cause. |
| **4. Check results** | The final full-suite run, or the last task's checks. A FAIL here after all tasks passed means tasks interfere. | Look at the warning in section 9; usually a new task or a spec fix. |
| **5. Diff stats** | Size per task. Large diffs deserve the closest review. | — |
| **6. Budget** | Agent calls used, wall-clock, cost (Claude Code reports it). | Raise `budget.*` in `.semipilot/config.yaml` only if the work was genuinely larger. |
| **7. Infrastructure** | Harness, transient failures, outage minutes, whether the breaker tripped. | Repeated outages → run later; `infra.retry_window` can resume once automatically. |
| **8. Critic rejections** | What the plan critics rejected (also in `rejection-log.md`). | Recurring rejections → improve the instructions file or the cards. |
| **9. Warnings** | Locked-test edits that were reverted, out-of-scope files within tolerance, test-fixer contract edits (**review these**), tree resets. | A test-fixer edit must only change imports/names/signatures — check it. |
| **10–11** | Next steps and a PR description draft. | The user opens the PR. |

Files next to the report: `requirements.md`, `open-questions.md` (the answers), `implementation-plan.md` (tasks,
interfaces, *Knowledge Updates Required*), `plan.json`, `rejection-log.md`, `implementation-progress.json`
(checkpoint), and per-call logs in `.semipilot/runs/<run-id>/` (git-ignored; each log has the prompt, the agent's
answer, stdout, stderr and the classification).
