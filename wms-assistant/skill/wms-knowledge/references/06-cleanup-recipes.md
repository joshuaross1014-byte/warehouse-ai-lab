# 06 - Production cleanup recipes

Every recipe here is a **PRODUCTION WRITE**. The operating rule applies: show the statement and the rows it touches, back up (`SELECT * INTO dbo.bak_<topic>_<yyyymmdd>`), wrap in a transaction with count checks, get an explicit OK for that statement, read back afterwards, tag the first line `-- project: NAME`. Confirm with the floor before touching anything an operator might be working on. Each recipe was executed on a live instance.

## 1. Stuck wave whose orders were shipped or invoiced manually in the ERP

Symptom: wave sits R on the wave screen; `usp_afo_hold_wave` and `usp_afo_unbuild_wave_data` throw "Picking has started"; `usp_ww_cancel_order` rejects orders with STAGED/PICKED/LOADED picks.

Per wave (wh + wave_id), one transaction:
1. Pre-flight: no `t_work_q_assignment` via `pick.work_q_id`; no PRINTED/REPRINTED labels; `MANIFEST_SYSTEM`, `HJSHIP_INSTALLED`, `CONTAINER-OPTIMIZE` off for the wh.
2. `UPDATE t_pick_detail SET picked_quantity=0, staged_quantity=0, loaded_quantity=0 WHERE wh_id=@wh AND wave_id=@w;` (records only; moves no stock; defeats the guard).
3. `EXEC usp_afo_hold_wave @wh, @w, @msg OUT;` expect 'SUCCESS'.
4. `EXEC usp_delete_wave @wh, @w, @msg2 OUT;` expect 'NONE' (= no error).
5. `DELETE t_afo_wave_detail_line` (join by wave_detail_id) then `DELETE t_afo_wave_detail` for the wave, or it still shows on the grid and the autowave regenerates picks from the recipe.
6. Open status-N orders left on the wave that must not re-wave: `UPDATE t_order SET status='B', actual_ship_date=GETDATE() WHERE status='N' AND order_number IN (...)` (mirrors the cancel proc).

Risk: if the order is still flagged for export and open in the ERP it will re-export.

## 2. Flow-through order shipped but STAGED picks linger

Symptom: next day's wave for the same item collides; scanner shows the item but will not advance; work-queue summary cluttered (status U). The floor cannot self-clear because Delete Wave needs Hold and Hold refuses `staged_quantity > 0`.

Steps 1-4 of recipe 1 for each orphaned wave whose order is already S/D (**never a live N order**). Order headers are not touched.

If the order must fully disappear (the ERP sent a `processing_code='Delete'` that errored and does not retry): in one transaction `DELETE t_afo_wave_detail_line` -> `t_afo_wave_detail` -> `t_order_detail` -> `t_order_comment` -> `t_order` (wh_id + order_number) -> `UPDATE t_al_host_order_master SET import_status='S', error_msg=NULL` for the stuck Delete row. Do not re-drive `usp_al_import_order` (its Delete path treats picks/waves as blocking guards).

## 3. Orphan RELEASED picks pinning stock

Mechanism: a shipped order leaves RELEASED/unallocated picks; the allocation engine does not filter orders already S/D, so a later run pins live stock to the dead pick; the next live order allocates 0 and ships short; repeat. On-site "hold -> release LP -> replan" only frees stock for the next dead pick.

Detect: `t_pick_detail.status='RELEASED'` joined to `t_order.status IN ('S','D')`; RELEASED picks with no `t_allocation` row older than a few hours.

Clean (single transaction per shipped order): `DELETE t_allocation` rows joined to the order's picks -> `UPDATE` those picks RELEASED -> CLOSED (leave quantities) -> `UPDATE t_work_q SET work_status='C'` for their queues. Then cycle-count the bin (unscanned cases often shipped physically = phantom stock) and reconcile the ERP delivery line.

**Do not automate this on order status alone.** A janitor gated only on `pkd.status='RELEASED' AND user_assigned IS NULL AND o.status IN ('S','D')` closed live partial-shipment work within 15 minutes of a partial ship-confirm, because ship-confirm sets S regardless of fill rate and "ship what is ready, keep picking, ship the rest" is a routine floor pattern. Open design question before any redesign: what distinguishes excess allocation for demand already met from demand still owed. A strict line-level gate (`ISNULL(od.qty_shipped,0) >= od.qty`) may be too strict to solve the original problem; a grace period on `actual_ship_date` is the weaker but safer mitigation. Keep any such proc's preview flag defaulting to dry-run.

## 4. Outbound pallets received into receiving staging

Three steps per LP, all required:
1. `EXEC dbo.usp_move_lp` receiving staging -> outbound staging (pass the LP's current parent; verify both `t_stored_item` and `t_hu_master` moved; it writes no tran_log, so record the move in a file).
2. `UPDATE t_hu_master SET type='SO' WHERE wh_id=@wh AND hu_id=@dlp AND type='IV';` (the receipt re-typed it; IV pallets are invisible to loading).
3. `INSERT INTO t_load_split_detail (wh_id, load_id, order_number, hu_id, destination) SELECT @wh, @order, @order, @dlp, o.ship_to_code FROM t_order o WHERE ...;` (`seq_id` is identity; destination from `t_order.ship_to_code`, never hardcoded). The receipt deleted the row; without it Load by Destination finds nothing.

Sibling cases: SO pallets stranded on a fork after an abandoned 321 -> `usp_move_lp` fork -> outbound staging (keeps type SO) + re-insert the load-split row; the abandoned 321 also traps the operator's next Move. Physically shipped but unrecorded: check the ERP order first; if open, re-load and Ship via RF so the ERP gets the delivery (do not zero out).

## 5. Inventory stranded under a template-token LP

Serial item, so delete in FK order: `t_serial_number` (by sto_id) -> `t_stored_item` -> orphan `t_hu_master` (wh_id + hu_id) -> reset `t_rcpt_ship_po_detail.received_qty = 0` for that shipment + item. Safe only when the receipt is not reconciled (`reconciled_date IS NULL`) and `reserved_for IS NULL`. Root cause is client-side; this only clears the symptom.

## 6. LPN attached to item-managed staging stock

Symptom: gun loops on the same item; picks RELEASED with `picked_quantity 0` for a long time; stock, serials, allocation all healthy. Confirm `t_location.item_hu_indicator='I'` and find the LP via `t_stored_item.hu_id IS NOT NULL` at that location.

Fix: `UPDATE t_stored_item SET hu_id = NULL WHERE sto_id IN (...)`, guarded with an abort if `picked + staged + loaded + shipped <> 0` (operator live) or if `@@ROWCOUNT` differs from the expected count. Leave the `t_hu_master` headers as orphans (trivial rollback = set hu_id back). Safe because: no triggers on `t_stored_item`/`t_hu_master`; serials ride on `sto_id`; `t_allocation` keys on `pick_location` (no hu column); the ERP already received the receipt with hu_id NULL; staging is type S with a large capacity so no Full-flag recalculation. Do not release a work-queue slot on the evidence of `workers_assigned=1` with NULL `user_assigned` alone; that slot can be a live picker.

Systemic guard idea: block or warn on HU creation when the put location's `item_hu_indicator='I'`; monitor `t_stored_item.hu_id IS NOT NULL` at item-managed locations.

## 7. Stranded multi-order batch after an RF reset

Symptom: "NO WORK IS AVAILABLE" on every scanner while the batch's remaining lines are RELEASED and allocated. Cause: the worker slot stayed held (`t_work_q.workers_assigned >= workers_required`). Remedy (after the supervisor confirms nobody is on it): `UPDATE t_work_q SET work_status='U', workers_assigned = workers_assigned - 1 WHERE work_q_id = @q`. Harden `usp_reset_device_picking` to do this at reset time (reference 05). Separate genuinely unallocatable lines from the assignment problem first.

## 8. "Says shipped but never picked"

Not a data fix: match the order's `actual_ship_date` to a `t_tran_log` tran 950 row (Cancel Outbound Order). If asked to change behaviour: customise `usp_ww_cancel_order` to leave `actual_ship_date` NULL on 'B', or add a 950 indicator to the page.

## 9. Closed/cancelled ERP transfer request still open in the WMS

Recon: OWTQ `DocStatus='C'` or `CANCELED='Y'` with no WTQ1.TrgetEntry vs WMS `t_order type_id=32 status='N'`. Those with a transfer drawn are harmless. For the genuine leftovers, cancel in the WMS (hold if waved, then cancel) so the autowave cannot pick them up. Until the integration sends Delete for transfers, run this as a monitor.

## 10. Cross-environment item copy (PROD -> TEST)

Linked server on TEST; `INSERT ... SELECT FROM [PROD].<db>.dbo.<table>` on TEST in `WHILE @@ROWCOUNT>0 / INSERT TOP(1000)` loops with `NOT EXISTS` guards. Insert `t_item_master` without the identity, then children joining on item_number + wh_id to pick up the new `item_master_id`. Pre-existing FKs: `t_whse`, `t_class` (warehouse-scoped), `t_pick_put_master`, `t_item_xdock_profile`, `t_attribute_collection_master`, `t_client`. Collation is case-sensitive.

## Verification habits that caught wrong calls

- Read the issue log before diagnosing a familiar symptom (symptom-worded titles).
- Confirm the operator is not live on the record before zeroing or releasing anything.
- Prefer leaving orphan headers over extra deletes when rollback becomes simpler.
- Record manual moves that write no tran_log in the project folder.
- After the fix, watch the next real transaction on the floor (a clean 301/302 twenty minutes later is the proof).
