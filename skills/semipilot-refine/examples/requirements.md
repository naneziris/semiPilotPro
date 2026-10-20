---
feature: export-orders-csv
type: feat
status: draft
---
# Requirement: Export the orders list as CSV

## Problem
Shop admins reconcile orders in spreadsheets and currently copy rows by hand from the orders table, which is slow
and error-prone for more than a page of results. They need the list they are looking at — with its filters — as a
file they can open in a spreadsheet.

## In Scope
- An "Export CSV" action on the admin orders list.
- The export contains the columns visible in the orders table, in the same order, with the same filters applied.
- A cap of 10 000 rows, with a message when the cap truncates the export.

## Out of Scope
- Other formats (XLSX, PDF).
- Scheduled or emailed exports.
- Exporting order line items or customer records.

## Impact Analysis
**Confirmed tags:** orders, admin-ui

**Modules / cards touched:**
| Module or card | Why touched | Public contracts at risk | Breakage risk |
|---|---|---|---|
| `shop.orders` | query reused for the export | `listOrders(filters)` signature | low |
| `shop.admin-ui` | new action on the orders list | none | low |

**Invariants that constrain this change:** "Order queries always go through `listOrders()`; never query the orders
table directly" (shop.orders).

**Tests that exercise the touched surface:**
- `tests/orders/test_list_orders.py` — covers filtering and paging of `listOrders()`

**Side-effect surfaces (state, providers, event handlers, lifecycle hooks):**
- none

**Confidence:** high.

## Acceptance Criteria
1. Exporting a filtered list of 3 orders produces a CSV with a header row and exactly those 3 orders [check: test_export_respects_filters]
2. The CSV columns and their order match the visible columns of the orders table [check: test_export_columns_match_table]
3. Exporting an empty list produces a CSV with only the header row [check: test_export_empty_list]
4. Exporting more than 10 000 matching orders returns the first 10 000 and the message "Export truncated to 10 000 rows" [check: test_export_truncates_at_10000]
5. Values containing commas, quotes or newlines are escaped per RFC 4180 [check: test_export_escapes_csv_values]

## Assumptions
- "Visible columns" means the default column set; per-user column customisation does not exist yet.

## Open Questions
- Should the file name include the date? — default: yes, `orders-YYYY-MM-DD.csv`

## Knowledge References
- Tags: orders, admin-ui
- Cards resolved: docs/cards/orders.md, docs/cards/admin-ui.md
- Knowledge updates expected: docs/cards/admin-ui.md (new action), docs/CHANGELOG.md
