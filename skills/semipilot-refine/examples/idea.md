# Example input

What the user typed:

```
/semipilot-refine let shop admins export the orders list as CSV
```

The repository has a knowledge layer. The refiner proposed tags `orders` and `admin-ui` from
`docs/cards/_vocabulary.md`, the user confirmed both, and the refiner asked three questions:

1. Which columns — the ones visible in the orders table, or the full order record?
2. Should the export respect the filters currently applied to the list?
3. Is there a size limit we must stay under (some admins have 50k+ orders)?

The user answered: "visible columns only; yes, respect filters; cap at 10 000 rows with a message".

The resulting file is [requirements.md](requirements.md).
