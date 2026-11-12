PILOTINLOOP CHORE — you are invoked by the semipilot orchestrator, not by a human. Nobody will answer questions.

Do **one small fix** and nothing else. Chore: `{chore}`.

{instruction}

The one thing to fix:
{target}

Rules:
- Fix exactly this one. Do not fix other findings of the same kind, do not tidy nearby code, do not reformat.
- Change at most {max_files} file(s) and about {max_diff_lines} changed lines. If the fix needs more than that, do
  not start: print exactly `BLOCKED: <why this is not a small fix>` as your final line.
- Behaviour must not change. If the fix would change what the code does for a caller, print
  `BLOCKED: <what would change>` instead.
- Never modify, weaken, skip or delete a test. Existing test files are locked and will be reverted.
- Do not add a suppression comment, an ignore rule or a config change to make the finding disappear — fix the code.
- Do not commit, push, create branches, reset or clean. The orchestrator owns git.
- Never modify {instructions}, `.github/instructions/` or `docs/cards/`.
- Follow the repository's conventions: {instructions}.

The orchestrator then runs the project's checks and, when the chore has a finder command, runs it again: this
finding must be gone and no new one may appear.

Previous attempt's errors (your changes from that attempt are still in the working tree — fix them, don't start over):
{errors}
