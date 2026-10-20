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

> Ready. In a separate terminal on `main`, on a machine that stays awake:
> `caffeinate -i semipilot run export-orders-csv`. It creates `feat/export-orders-csv`, never pushes, and
> leaves a report. Tell me when it finishes and I'll walk you through it.

**Later — user:** done, what happened?

**Agent** runs `semipilot review export-orders-csv` and summarises: stop reason `completed`; one assumption (D-1:
the truncation message is shown as a toast, reversible in `admin/orders_view.py`); 4/4 tasks done; final full suite
PASS; one warning — the test-fixer renamed an import in `tests/orders/test_export.py` (review it: it should only
change the import line). Suggests: review the four commits, then `/semipilot-scribe export-orders-csv`, then open
the PR.
