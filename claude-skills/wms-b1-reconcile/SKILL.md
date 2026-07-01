---
name: wms-b1-reconcile
description: Reconcile sales-order flow between the ERP (SAP B1) and the WMS to surface drift — orders open+flagged for the WMS in the ERP that never reached the floor (forward drift), and orders shipped/done in the WMS but still open in the ERP (reverse / ship-confirm backflow drift). Use to investigate "order missing from WMS", stuck orders, or as a scheduled cross-system integrity check.
---

# WMS ↔ ERP Order Reconciliation

Cross-checks the ERP→WMS→ERP order round-trip. The two systems are on different
engines (ERP on HANA, WMS on SQL Server), so there is no single cross-join — pull
keys from one side, probe the other, diff in-app.

## Join facts (adapt to your setup)

- **Join key:** WMS `t_order.order_number` == ERP `ORDR."DocNum"` (cast: WMS is
  text, DocNum is integer).
- **Warehouse:** ERP `RDR1."WhsCode"` maps to WMS `t_order.wh_id` (often 1:1).
- **WMS flag:** a header UDF on `ORDR` marks orders destined for the WMS; only
  reconcile those.
- **ERP status:** `DocStatus='O'` open / `'C'` closed; `CANCELED='Y'` cancelled.
- **WMS status flow:** new → picking started → waved → done/shipped.
- One WMS instance may serve multiple ERP companies — reconcile only the
  warehouses fed by the ERP database you query.

## Scope to keep result sets small

Thousands of orders are open at any moment (most just in-flight). Constrain by
**warehouse + an aging window** (e.g. open > 2h) so you compare a small set.

## Step 1 — ERP: open, WMS-flagged orders for one warehouse (read-only)

Return a compact list of order numbers (e.g. `STRING_AGG`) for orders that are
open, not cancelled, WMS-flagged, in the target warehouse, older than the aging
cutoff.

## Step 2 — WMS: probe those order numbers (read-only)

```sql
SELECT d.dn, o.status AS wms_status, s.import_status, s.error_msg
FROM @docs d
LEFT JOIN dbo.t_order o WITH (NOLOCK) ON o.order_number = d.dn AND o.wh_id = :wh
OUTER APPLY (SELECT TOP 1 import_status, error_msg
             FROM dbo.t_al_host_order_master m WITH (NOLOCK)
             WHERE m.order_number = d.dn AND m.wh_id = :wh
             ORDER BY m.record_create_date DESC) s;
```

## Step 3 — Classify

**Forward drift** (ERP open+flagged, not progressing in WMS):
- WMS row missing AND no staging row → never reached WMS (export gap) → re-export.
- WMS missing AND staging error → import failed → fix root cause (see
  `wms-import-errors`), then re-export.

**Reverse drift** (WMS finished, ERP not updated):
- WMS status = done but ERP still open beyond a grace period → ship-confirm/delivery
  not flowing back → check the WMS→ERP return queue.

In-flight (picking/waved) with a matching open ERP order = healthy, not drift.

## Step 4 — Report

Per warehouse: total checked, healthy count, and only the drift rows with their
classification + action. State a clean warehouse plainly.

## Monitor mode

Loop the warehouses for the queried ERP company; alert only on forward-drift
(missing/failed) or reverse-drift beyond the grace period. Read-only across both.
