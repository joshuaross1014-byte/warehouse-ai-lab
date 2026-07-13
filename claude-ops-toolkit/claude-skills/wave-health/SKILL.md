---
name: wave-health
description: WMS wave & staged-inventory health check — stuck/stale waves, serial-completeness mismatches (serial-managed pallets where serial count <> qty), and autowave duplicate-wave detection. Use to investigate stuck waves, stranded serialized inventory blocking the ERP receipt/delivery, or as a scheduled WMS floor-health monitor.
---

# WMS Wave & Staged-Inventory Health

Three independent read-only checks. Run all for a full sweep, or one for a specific
symptom.

## Schema notes

- Wave header `dbo.t_wave_master`: `wave_id`, `status` (N=new, H=hold,
  A=allocating, R=released), `wh_id`, `created_date`, `released_date`, ship dates.
- Staged inventory `dbo.t_stored_item`: `sto_id`, `item_number`, `wh_id`,
  `actual_qty`, `hu_id` (LPN), `shipment_number`.
- Serials `dbo.t_serial_number` linked by `sto_id`; item master
  `dbo.t_item_master` (`serial_control='F'` = serial-managed).

## Check 1 — Stuck / stale waves

A naive ">24h and not released" filter returns a large historical backlog of
orphaned open waves — that's data hygiene, not a daily signal. The **sharp** signals:

```sql
-- allocating waves stuck > 2h (hung allocation) — investigate first
SELECT wh_id, wave_id, DATEDIFF(hour,created_date,GETDATE()) AS age_h
FROM dbo.t_wave_master WITH (NOLOCK)
WHERE status='A' AND released_date IS NULL AND created_date < DATEADD(hour,-2,GETDATE());

-- RECENT waves past their ship date (excludes the historical junk)
SELECT wh_id, status, wave_id, created_date, latest_ship_date
FROM dbo.t_wave_master WITH (NOLOCK)
WHERE status IN ('N','H','A') AND released_date IS NULL
  AND latest_ship_date < GETDATE() AND created_date >= DATEADD(day,-3,GETDATE());
```
Aged N/H waves may be intentional (autowave holds them until release; once-a-day
warehouses park them) — weigh against the warehouse's release schedule.

## Check 2 — Serial-completeness mismatch

Serial-managed pallets where captured serial count ≠ on-hand qty (interrupted RF
scans). This strands inventory and blocks the ERP receipt/delivery.

```sql
SELECT si.wh_id, si.item_number, si.hu_id AS lpn, si.actual_qty,
       COUNT(sn.serial_number_id) AS serial_cnt, si.shipment_number
FROM dbo.t_stored_item si WITH (NOLOCK)
JOIN dbo.t_item_master im WITH (NOLOCK)
     ON im.item_number=si.item_number AND im.wh_id=si.wh_id AND im.serial_control='F'
LEFT JOIN dbo.t_serial_number sn WITH (NOLOCK) ON sn.sto_id=si.sto_id
WHERE si.actual_qty > 0
GROUP BY si.wh_id, si.item_number, si.hu_id, si.actual_qty, si.shipment_number
HAVING COUNT(sn.serial_number_id) <> si.actual_qty;
```
Fix: re-capture the missing serials on that LPN, then re-export to post the ERP
receipt/delivery. (Pairs with a reconcile-time guard that blocks completing such a
pallet.)

## Check 3 — Autowave duplicate waves

If autowave *merges* a second run into an existing open wave for the same key,
duplicates suggest the merge guard missed. Note: `COUNT(*) > 1` open waves per
warehouse is NOT a duplicate signal (normal operation). A real check must group by
the **order-level merge key** (e.g. promised_date + ship-to + channel) by joining
waves to their orders, and flag keys with >1 open wave. Scope to autowave-enabled
warehouses only.

## Report / Monitor mode

Per check: clean vs flagged; itemize only the flagged rows + action. On a schedule,
alert on any stuck 'A' wave, any recent wave past its ship date, and any
serial-completeness mismatch (should be 0). Read-only throughout.
