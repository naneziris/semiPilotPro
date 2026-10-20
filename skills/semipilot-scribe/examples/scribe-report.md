# Example — scribe after `export-orders-csv`

Work list from `implementation-plan.md`:

```
## Knowledge Updates Required
- docs/cards/admin-ui.md: new "Export CSV" action on the orders list; public contract: GET /admin/orders.csv
- docs/cards/orders.md: no change
- docs/decisions.md: no change
- docs/dependencies.md: no change
- docs/CHANGELOG.md: Shop admins can export the orders list as CSV
```

Edit to `docs/cards/admin-ui.md` (surgical — two lines):

```diff
 public_contracts:
   - "Admin routes are under /admin and require the admin role"
+  - "GET /admin/orders.csv?<list filters> returns at most 10 000 rows (text/csv, RFC 4180)"
 code:
   - src/admin/
 ...
-The admin UI lists, filters and edits orders and products.
+The admin UI lists, filters, edits and exports (CSV) orders, and edits products.
```

Verification and report:

```
### SCRIBE REPORT
Files updated:
- docs/cards/admin-ui.md: added the CSV export contract; prose mentions export
- docs/cards/manifest.json: regenerated
- docs/CHANGELOG.md: "Shop admins can export the orders list as CSV, with the list's filters applied (up to 10 000 rows)."

Verification:
- kb validate: pass
- kb guard: all touched cards covered (admin-ui updated; orders listed as "no change", code untouched)
- kb drift: clean

Gaps noticed (not auto-fixed):
- none
```
