---
name: wms-empty-po
description: Diagnose a WMS inbound PO that appears empty / has 0 lines (header imported but detail lines failed). Traces the failure to an ERP item not syncing to the WMS because of missing item flags, and prescribes the fix. Use when a PO shows in the ERP but is empty in the WMS, or for "invalid item-warehouse combination" inbound errors.
---

# WMS Empty Inbound PO — Item Sync Diagnosis

An inbound PO that shows in the ERP but is **empty (0 lines)** in the WMS almost
always means the PO **header** imported but the **detail lines failed**. WMS detail
import is typically **all-or-nothing** — one bad line rejects the whole batch, so
good lines show a cascade message (`At least one detail row failed validation`)
while the real culprit shows `Invalid Item-Warehouse combination` (the item is not
in the WMS item master for that warehouse). Root cause is usually an **ERP item not
syncing to the WMS**.

## Step 1 — Confirm the header/detail split (WMS, read-only)

```sql
SELECT po_number, display_po_number, wh_id, import_status, error_msg, record_create_date
FROM dbo.t_al_host_po_master WITH (NOLOCK) WHERE po_number = :po;

SELECT item_number, wh_id, import_status, error_msg
FROM dbo.t_al_host_po_detail WITH (NOLOCK) WHERE po_number = :po
ORDER BY import_status DESC;
```
Header success + detail `Invalid Item-Warehouse combination` = classic empty-PO.
Note the offending item(s) and warehouse.

## Step 2 — Classify the failed item FIRST (avoid misdiagnosis)

Not every failed line is a broken sync. **Non-inventory items** (freight, charges,
landed cost) legitimately fail WMS import — you don't pick/ship a charge. Check the
ERP item master:

```sql
SELECT "ItemCode","ItemName","InvntItem","U_AttributeManaged", <per-warehouse-flag>
FROM "OITM" WHERE "ItemCode" IN (:items);
```

- **`InvntItem='N'`** (freight/charge/landed-cost): **benign** — expected failure,
  do NOT change item flags. If a PO's only lines are non-inventory, it has nothing
  WMS-relevant; the real question is whether the ERP should export a charge-only PO
  to the WMS at all (an ERP-side export filter).
- **`InvntItem='Y'`** (real physical item): proceed to Step 3.

## Step 3 — Check the sync gate flags (ERP, read-only)

For inventory items, two flags typically gate whether an item drops into a WMS
warehouse:

1. An **attribute/serial-managed flag** on the item (gates whether it exports at all).
2. A **per-warehouse enablement flag** (routes the item to that warehouse).

Both must be set. A common misconfiguration tell: an expiry-controlled item with
the attribute flag off.

## Step 4 — Prescribe the fix (do NOT auto-apply; ERP master data)

Set both flags on the item(s) in the ERP, **then re-export/re-save the PO** —
inbound POs are send-on-change, so old failed detail rows do not reprocess
themselves. Verify the item lands in the WMS item master next cycle, then re-check
the PO detail rows.

Read-only diagnosis. Related: `wms-import-errors`, `wms-b1-reconcile`.
