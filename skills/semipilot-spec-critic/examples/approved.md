# Example — APPROVED, then approval recorded

```
### SPEC-CRITIC: APPROVED
Notes for the reviewer: the 10 000-row cap is a product decision — confirm it with whoever owns the admin UI.
Acceptance criteria (verbatim):
1. Exporting a filtered list of 3 orders produces a CSV with a header row and exactly those 3 orders [check: test_export_respects_filters]
2. The CSV columns and their order match the visible columns of the orders table [check: test_export_columns_match_table]
3. Exporting an empty list produces a CSV with only the header row [check: test_export_empty_list]
4. Exporting more than 10 000 matching orders returns the first 10 000 and the message "Export truncated to 10 000 rows" [check: test_export_truncates_at_10000]
5. Values containing commas, quotes or newlines are escaped per RFC 4180 [check: test_export_escapes_csv_values]
→ Reply `approve` to approve the spec, or tell me what to change.
```

The user replies `approve`. The skill changes one line in the frontmatter:

```diff
 ---
 feature: export-orders-csv
 type: feat
-status: draft
+status: approved
 ---
```

and answers:

> Approved. Next, in a terminal on your base branch: `semipilot preflight export-orders-csv` (the planner's
> questions), then `semipilot run export-orders-csv`.
