---
name: so-price-gap
description: Diagnose sales orders that import with blank/zero unit price due to a regional price-list propagation lag. Scans for items priced in a region's source list but missing from the region's price list, and triages blank-priced order lines. Use for "order has blank unit price" tickets, or as a scheduled pre-import price-coverage check.
---

# Sales-Order Blank-Price (Regional Price-List Propagation Gap)

Recurring symptom: regional orders import with **blank unit price** even though the
item is priced elsewhere. Root cause is usually a **price-list propagation gap**,
not a missing price.

## Topology (verify at runtime — it drifts)

In a multi-region B1 setup, each region prices off its own **base price list**,
which is **copied** from a source list by an external/scheduled job (not native
B1). Each region declares its own source — do not assume one source for all.

```sql
SELECT "ListNum","ListName","BASE_NUM","U_Location","U_BasePriceList"
FROM "OPLN" WHERE "ListName" LIKE '%Base%' ORDER BY "ListNum";
```
`U_BasePriceList` tells you each region's source list. The copy job lags/incomplete,
so the morning batch imports before it catches up → blank lines. B1 never
auto-reprices existing orders, so they stay blank until re-determined.

## Step 1 — Measure the gap per region (leading indicator)

For each region, count items priced in its **source** but blank in the region list:

```sql
WITH s AS (SELECT "ItemCode" FROM "ITM1" WHERE "PriceList"=:src AND "Price">0),
     r AS (SELECT "ItemCode" FROM "ITM1" WHERE "PriceList"=:region AND "Price">0)
SELECT (SELECT COUNT(*) FROM s) AS src_priced,
       (SELECT COUNT(*) FROM r) AS region_priced,
       (SELECT COUNT(*) FROM s WHERE "ItemCode" NOT IN (SELECT "ItemCode" FROM r)) AS gap_items
FROM DUMMY;
```
A large `gap_items` = many items that will blank-price for that region.

## Step 2 — Triage a specific blank-priced order

```sql
SELECT h."DocNum", l."ItemCode", l."Price", l."PriceList"
FROM "ORDR" h JOIN "RDR1" l ON l."DocEntry"=h."DocEntry"
WHERE h."DocNum" = :docnum AND (l."Price" = 0 OR l."Price" IS NULL);
```
For each blank line, confirm the item is priced in the source but not the region's
list → confirms propagation lag, not a genuinely unpriced item.

## Step 3 — Report & fix direction

- **Immediate:** re-determine prices on the blank lines once the region's list is
  caught up (B1 won't do this automatically for existing orders).
- **Root cause:** ensure the source→region copy job completes **before** the
  regional order import, and backfills the full gap.

## Monitor mode

Run Step 1 across all regions **before** the morning import; alert if any region's
gap exceeds a threshold. Track the day-over-day delta so a growing gap stands out
from a chronic baseline. Read-only — never write price lists or orders.
