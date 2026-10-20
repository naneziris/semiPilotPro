# `kb resolve` in practice

Task: "add a 'refunded' filter to the admin orders list". The agent picks tags `orders` and `admin-ui` from the
vocabulary, the user confirms, and the agent runs:

```
$ python3 scripts/kb/kb.py resolve --tags orders,admin-ui
# kb resolve — tags: orders, admin-ui
# matched: shop.admin-ui, shop.orders
# expanded (one hop): shop.auth, shop.db, shop.reports

## Read these cards (L1)
docs/cards/admin-ui.md
docs/cards/auth.md
docs/cards/db.md
docs/cards/orders.md
docs/cards/reports.md

## Deep docs if the card points you there (L2)
docs/deep/order-status-machine.md

## Code paths — execution time only (L3)
src/admin/  (shop.admin-ui)
src/auth/  (shop.auth)
src/db/  (shop.db)
migrations/0007_orders.sql  (shop.orders)
src/orders/  (shop.orders)
src/reports/  (shop.reports)
```

What the agent does with it:

1. Reads the five cards in full (~2 500 tokens). `reports` came in as a reverse dependent of `orders` — it consumes
   `listOrders()`, so a filter change could affect it; the impact brief must say whether it does.
2. Reads `order-status-machine.md`, because "refunded" is a status and the orders card points there.
3. Notes the invariants it must honor ("every order query goes through `listOrders()`") before planning.
4. Opens `src/orders/service.ts` and `src/admin/orders-list.tsx` only when implementing.

The same tags produce the same list tomorrow, for every agent and every reviewer.
