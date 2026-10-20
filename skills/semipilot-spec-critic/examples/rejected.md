# Example — REJECTED

Reviewing `.semipilot/features/export-orders-csv/requirements.md` (draft, most recently modified).

```
### SPEC-CRITIC: REJECTED
Required fix: Criterion 4 ("Large exports are handled") is not observable and has no [check:] tag — state the cap and the message, e.g. "Exporting more than 10 000 matching orders returns the first 10 000 and the message 'Export truncated to 10 000 rows' [check: test_export_truncates_at_10000]".
Also: In Scope promises "the same filters as the list", but no criterion proves it — add one with [check: test_export_respects_filters].
Also: The impact analysis lists tests/orders/test_export.py, which does not exist; list the tests that do (tests/orders/test_list_orders.py).
Reasoning: An unattended loop builds exactly what the criteria prove. Criterion 4 cannot be turned into a locked test, and the filter behaviour would be left to the implementer's guess even though the card shop.orders says every order query goes through listOrders(filters).
→ Run /semipilot-refine again with this fix.
```
