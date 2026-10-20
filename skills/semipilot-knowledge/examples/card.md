---
id: shop.orders
owns: [orders, order-search]
depends_on: [shop.db, shop.auth]
public_contracts:
  - "listOrders(filters: OrderFilters, page: Page) -> OrderPage  (src/orders/service.ts)"
  - "orders table schema (migrations/0007_orders.sql)"
code:
  - src/orders/
  - migrations/0007_orders.sql
docs:
  - docs/deep/order-status-machine.md
invariants:
  - "Every order query goes through listOrders(); never query the orders table directly (ADR-004)"
  - "Order status changes only via transition(); direct writes skip the audit log"
  - "Money is integer cents everywhere; never floats"
---
Orders owns the order lifecycle: creation from a checkout, the status machine (pending → paid → shipped → closed,
with cancel/refund branches), and every read of orders through `listOrders()`, which applies tenant scoping and the
admin filters. Writes go through `transition()`, which validates the status machine and writes the audit log in the
same transaction. Search (`order-search`) is a thin layer over `listOrders()` with full-text matching on customer
name and order number. The status machine and its edge cases are in the deep doc.
