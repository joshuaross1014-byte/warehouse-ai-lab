---
name: wms-import-errors
description: Triage WMS host-order import failures, filtering out benign wave/picking lock rejections to surface only real import errors. Use when investigating stuck/failed order imports from the ERP, or as a scheduled WMS inbound-queue health check.
---

# WMS Host Order Import-Error Triage

Surfaces **genuine** order-import failures in the host→WMS staging table, separating
them from the high-volume benign rejections that dominate the error status.

## Why filtering matters

The ERP re-exports orders frequently and tries to overwrite the WMS copy. Once an
order is being allocated / waved / picked, the WMS **correctly refuses** the
update. These refusals are logged as import errors but are working as designed —
on a normal day they are the vast majority of error rows. The benign messages are
product-standard, e.g.:

- `Picking has started - cannot make changes to this order`
- `Order is already added to wave - cannot make change to this order`
- `Order is being allocated - cannot make changes to this order`

**Wrinkle:** a real error is often *concatenated* with a benign one in the same
message (pipe-separated). So a simple `NOT IN (benign list)` filter MISSES real
errors. The query below **strips** the benign phrases + separators and keeps any
row with a non-empty residual — that residual is the real error.

## Step 1 — Triage query (read-only)

```sql
;WITH e AS (
  SELECT display_order_number, wh_id, customer_code, record_create_date,
    residual = LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(REPLACE(error_msg,
        'Picking has started - cannot make changes to this order',''),
        'Order is already added to wave - cannot make change to this order',''),
        'Order is being allocated - cannot make changes to this order',''),
      '|','')))
  FROM dbo.t_al_host_order_master WITH (NOLOCK)
  WHERE import_status = 'E'
    AND record_create_date >= DATEADD(day, -3, GETDATE())
)
SELECT residual AS real_error, COUNT(*) AS cnt,
       MIN(record_create_date) AS first_seen, MAX(record_create_date) AS last_seen
FROM e WHERE LEN(residual) > 0
GROUP BY residual ORDER BY cnt DESC;
```

## Step 2 — Interpret

| Residual pattern | Meaning | Action |
|---|---|---|
| `Invalid Warehouse ID ...` | Order references a warehouse not configured in WMS | Verify warehouse setup / ERP→WMS mapping |
| `... does not exist for Deletion` | ERP sent a delete for something WMS never had | Usually a benign race; confirm not live, then ignore |
| `Invalid Item-Warehouse combination` | Item not synced to that warehouse | Item-sync issue — see `wms-empty-po` |
| missing/invalid customer | Customer not in WMS master | Check customer master sync |
| anything else | Unclassified | Read the full message; check the order detail rows |

For a failed order, confirm whether it later succeeded (the ERP keeps retrying) —
a later success row means it self-healed; only error-only orders need action.

## Step 3 — Report

Total error rows, benign vs real, the real-error breakdown, and for each the
affected orders/warehouses + recommended fix. Do not alarm on benign counts.

## Monitor mode

On a schedule, report only if new real errors appear, or if any import is stuck
in-progress beyond ~15 min. Stay silent otherwise. Read-only — never run DML.
