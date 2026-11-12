# Risk tiers

Every requirements file names a tier in its frontmatter: `risk: low | medium | high`. The tier decides how much of
the run happens without the human — it is the answer to "if the loop gets this wrong, who finds out, when, and what
does it cost?". Propose one, give the reason in a sentence, and let the user change it.

| Tier | During the run the human… | Choose it when |
|---|---|---|
| `low` | does nothing: the checks are the gate, the review happens at the end | a wrong result is caught by the tests or is cheap to revert: UI copy, a pure function, an internal refactor with good coverage, a new isolated module |
| `medium` | reads `implementation-plan.md` once and runs `semipilot approve` before any code is written | a design decision in the plan will outlive the feature: a new table or API shape, a new dependency between modules, a change to a documented contract, anything the Impact Analysis rates *medium* |
| `high` | approves the plan **and** reads every task's commit before the next one starts | a wrong call is expensive and tests would not catch it: authentication and authorization, money, data migrations and deletion, public API contracts, anything the Impact Analysis rates *high* |

How to decide:

1. Start from the **Impact Analysis**: the highest *Breakage risk* in its table is the floor for the tier.
2. Ask what a green test run would **not** tell you. Security properties, data loss on real data, performance under
   load and "is this the right design" are not in the tests — if the change touches one, go up a tier.
3. Ask how the mistake would be **undone**. A reverted commit is `low`. A migration that ran, an email that went
   out, a contract a client already uses are not.
4. When two tiers both fit, pick the higher one and say what would let the user lower it (usually: a missing test).

Do not use `high` as a default to be safe. A person asked to read every commit of a harmless change stops reading
carefully, and then `high` means nothing when it matters.

The project can also raise the tier by path (`autonomy.escalate` in `.semipilot/config.yaml`): a plan that touches,
say, `**/auth/**` runs at least at `medium` whatever the requirements say. You cannot lower that; mention it when the
idea obviously touches such a path.
