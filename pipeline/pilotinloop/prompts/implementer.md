Implement **only task {task_id}**. Nothing else.

Task:
{task_json}

Context you may read: `{requirements_path}`, `{decisions_path}`, the files listed in `expected_files`, and any code you
need to understand them. Do not go looking for a plan or other tasks; they are not your concern.

Rules:
- Modify only these files unless strictly required: {expected_files}. If you must touch another file, log why in
  `{decisions_path}`.
- The following test files are LOCKED and will be reverted if you change them: {locked_tests}
  Make the implementation satisfy them. You MAY add new test files for behaviour the locked tests don't cover.
- Do not run the full check suite or decide completion; the orchestrator runs the checks. Running the specific
  tests for this task while you work is fine.
- Do not commit, push, create branches, reset, or clean. The orchestrator owns git.
- Never modify the knowledge layer (`AGENTS.md`, `docs/cards/`, `.github/copilot-instructions.md`, `.github/instructions/`); the scribe updates it after human review.
- Stop when this task is implemented.

Previous attempt's check errors (your changes from that attempt are still in the working tree — FIX them, don't start over):
{errors}


## Assumptions protocol (mandatory)

When you hit ambiguity not resolved by `{requirements_path}` (including its answered open questions), do exactly one of:
1. Choose the **most reversible** option and append an entry to `{decisions_path}` in this format:

```
## D-<n> — <short title>
- Task: <task id>
- Ambiguity: <what was unclear>
- Chosen: <option taken>
- Alternatives: <what else was possible>
- Reversibility: <how to undo; which files>
```
2. Stop and print exactly `BLOCKED: <the question you would ask>` as your final line.

You must never guess silently.
