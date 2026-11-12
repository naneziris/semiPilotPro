# Example session

**User:** the CSV export spec is approved, let's build it

**Agent** runs `semipilot preflight export-orders-csv`:

```
[09:12:03] knowledge layer healthy
[09:12:03] knowledge resolved for tags orders, admin-ui
[09:12:04] base: main @ 4d76158 → the run will create feat/export-orders-csv from here
[09:12:04] export-orders-csv: 5 tagged acceptance criteria, requirements approved, tree clean
[09:12:21] Claude Code OK

The planner has 2 question(s) before it can start:
  .semipilot/features/export-orders-csv/open-questions.md
```

**Agent:** The planner wants two decisions before it plans:

1. *Where does the CSV serialisation live?* — recommended: a new `orders/export.py` next to `listOrders`.
2. *Column header text — the UI labels or the field names?* — recommended: the UI labels.

Fill in each `Answer:` line (copy the recommendation if it is right) and I'll re-run preflight.

**User:** both defaults are fine, go

**Agent** (after the user filled in the answers) runs preflight again → `Ready.` and replies:

> Ready. Open a terminal tab of your own (not this chat), on `main`, on a machine that stays awake:
> `caffeinate -i semipilot run export-orders-csv`. It creates `feat/export-orders-csv`, never pushes, and
> leaves a report. Tell me when it finishes and I'll walk you through it.

**Later — user:** done, what happened?

**Agent** runs `semipilot review export-orders-csv` and leads with the review packet: stop reason `completed`, risk
tier `low`, 4/4 tasks done, final full suite PASS; the reviewer agent says *ship, with notes*. Then the *Read first*
list, in order:

1. One assumption (D-1): the truncation message is shown as a toast — reversible in `admin/orders_view.py`. Is a
   toast what you want?
2. The reviewer's one **major**: `orders/export.py:41` builds the whole CSV in memory before sending it; fine at the
   10 000-row cap, a problem if the cap is ever raised. Worth a look, your call.
3. The test-fixer renamed an import in `tests/orders/test_export.py` — it should only have changed the import line.
4. `admin/orders_view.py` — largest change (+84/-3), where the filters are passed through.

Evidence table: all five criteria have a locked test that failed before the code existed.

**Agent:** That is where I would start. Shall we open `git show 9c1e2aa` (T1) and go commit by commit? I have not
verified the reviewer's finding myself — let's look at line 41 together.

**Later — user:** read it all, the toast is fine, open the MR

**Agent** runs `/semipilot-scribe export-orders-csv` first (the repository has a knowledge layer), then
`semipilot mr export-orders-csv` and reports the draft request's URL.
