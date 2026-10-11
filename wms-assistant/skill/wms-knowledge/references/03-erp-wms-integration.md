# 03 - SAP Business One (B1) to WMS integration

The pattern described is the HighJump/Accellos "SQL connector" integration for SAP Business One: batch and queue, not an API. Several B1 companies can feed one WMS; keep a table of which company feeds which warehouses.

## Architecture (batch/queue)

1. **B1 side**: UDFs on every goods-bearing document (ORDR, ODLN, OINV, ORIN, OPOR, OPDN, OPCH, OWTR, OIGE, OIGN): the export flag (`U_HJ`, 'Y' = destined for the WMS), the WMS key written back (`U_HighJumpID`), goods receipt/issue entries created on confirm, hold UDFs (often dormant). A staging schema on the B1 side may exist for other feeds; it carries no addresses.
2. **Transport**: a vendor integration product implemented as **one Windows service per interface** (vendor export, item export, sales order, purchase order, delivery note, GRPO import, invoice, stored-item, shipment, order-pick status). **Each service has its own ODBC target and schedule.** Repointing to a new WMS host means editing every service; restarting does not change a target. Logs live under the product's `Local` folder (turn on extra debug); the failure-notification recipient is often empty, so failures notify nobody. B1-side add-on logs exist per interface; a log with **no rows at all** means the service is not polling that company, `F` rows mean it polls but the WMS write fails.
3. **WMS host interface**: `t_al_host_*` staging + `t_al_host_sql_import_queue` / `_export_queue`, importer `usp_al_import_order` (batch-scoped by `host_group_id`, MERGE on wh_id + order_number), `usp_xml_import_outbound_order` (1:1 copy; `ship_to_code` is computed in the connector, not in SQL).
4. Downstream (B1 -> WMS): items (+uom/upc), vendors, sales orders, POs. Upstream (WMS -> B1): receipts -> GRPO, shipments -> Delivery, inventory adjustments. On-hand is reconciled, not shared. ERP owns cost/price/GL/order; WMS owns physical/bin/lot.

## Sales order flow and the lock

- Orders land in `t_al_host_order_master` within a couple of minutes of creation when the export flag is set. Successful import = `t_order` status N.
- B1 **re-exports every open order every few minutes** as `processing_code='UPDATE'` until it is waved. The importer's WHEN MATCHED overwrites ship-to/bill-to columns and resets status to N: any direct edit to `t_order` is reverted within minutes. Never redirect ship-to by editing `t_order`; fix it on the B1 document or in the connector mapping.
- Once waved or picking started, the WMS refuses the update with `import_status='E'` and `error_msg` "Picking has started - cannot make changes to this order" or "Order is already added to wave - cannot make change to this order". This is a guardrail working as designed. Side effect: a B1 edit made after waving never reaches the floor. **Monitor real failures by stripping those two phrases (and `|`) and alerting on the residual**; a NOT IN misses concatenated messages.
- B1 side of the same guard: the add-on writes a lock row per document and the transaction-notification procedure rejects update/cancel/close with "locked by WMS". Typically only a line **price** change is excepted. The lock table is a live list (rows deleted on release), not a history; stale locks accumulate for orders that never progress.
- Flipping the export flag from 'N' to 'Y' later is the only proven "do not export yet" lever; date-interval settings in the add-on are eligibility filters, not schedules.
- Cancel in the WMS (`usp_ww_cancel_order`) sets status B **and `actual_ship_date=GETDATE()`**, logs tran 950, and leaves `t_afo_wave_detail` so the order stays on its wave. Cancelled order numbers can never be re-imported; B1 must issue a new document number.
- Join facts: WMS `t_order.order_number` == B1 `ORDR.DocNum`; `RDR1.WhsCode` == `wh_id`; export flag 'Y' = expected in WMS. Reconcile only the warehouses fed by the company you query. Drift directions: **forward** (B1 open + flagged but missing/failed in WMS) and **reverse** (WMS D/S but B1 `DocStatus='O'`).

## Purchase orders and items

- Inbound POs are **send-on-change**, not continuous. Detail import is all-or-nothing: one bad line fails the batch; good lines show "At least one detail row failed validation", the culprit shows "Invalid Item-Warehouse combination on Inbound Order" (item not in `t_item_master` for that wh).
- An item exports to the WMS only when the add-on's attribute-managed UDF is set **and** the per-warehouse enablement UDF is set. Item export runs on an `OITM.UpdateTS` delta every few minutes. After fixing the item, the PO must be re-saved in B1; failed `t_al_host_po_detail` rows do not reprocess themselves.
- Classify first: non-inventory items (`OITM.InvntItem='N'`, freight and charges) legitimately fail with the same message. A PO whose only line is a charge is genuinely empty and correct.
- Benign PO 'E' noise: FK conflicts from re-export of an already-received PO; "Invalid Warehouse ID" for a non-WMS warehouse flagged for export. Typo years in B1 dates retry forever with ODBC 22007 until the document is fixed or closed.
- Restores leave old `po_number`s in a test WMS; a real export overwrites by number. Compare vendor + items, not po_number alone.

## Transfers (type 32)

- **B1 inventory-transfer-request close/cancel is never sent to the WMS** on this add-on (Delete rows exist for sales orders, none for transfers). A closed request stays N in the WMS and, where transfer autowave is on, gets waved, picked and shipped with no human in the loop; B1 cannot post the transfer against the closed base document and no error surfaces anywhere.
- Recon: OWTQ `DocStatus`/`CANCELED` + WTQ1.TrgetEntry vs `t_order type_id=32 status N`. Requests closed *with* a transfer drawn are harmless (fulfilled outside the WMS); those closed with none are genuine leftovers still pickable.
- Options: integration fix (send Delete on close), a WMS-side monitor, an autowave guard on closed requests, or the operator rule "cancel in the WMS first, then close in B1; never close inside the autowave window".

## Deliveries and receipts

- Ship-confirm staging = `t_al_host_shipment_master`; link `ODLN.U_HighJumpID = shipment_id`. Deliveries are posted by the connector via DI API under a dedicated B1 user.
- **Delivery posting is all-or-nothing per shipment**: `Documents.Add` is atomic and B1's block-negative-inventory setting rejects any line where on-hand would go negative, so one stock-short line blocks the whole document. Triage: shipped orders still `DocStatus='O'` with zero `DLN1` rows (BaseType 17) = failed delivery; compare `RDR1.OpenQty` vs `OITW.OnHand` per line; fix B1 stock; resubmit the interface from the WMS dashboard (`t_al_host_resubmit_log`).
- Fully shorted orders get `actual_ship_date` with `qty_shipped=0` and no ship-confirm; no delivery expected (benign).
- GRPO blockers: serial-managed pallets with serials <> qty (reference 05), 0-serial `t_al_host_receipt` lines.

## Drop-ship design constraint

The WMS carries no AR/bill-to; `ship_to_code` is a label derived by the connector from the ship-to name. Drop-ship (bill one party, ship to another) is solved on the B1 document or in the connector mapping, never with a WMS scheduler. Ship-to is header-level in both systems; item-level drop-ship requires splitting onto separate documents upstream.

## Health-check pointers

- Queue health: count `t_al_host_order_master` by `import_status` and `processing_code` in the last hour; residual-strip the benign lock messages; alert on imports stuck 'I' > 15 minutes.
- Cutover lesson: zero inbound rows after a restore meant some of the per-interface services still pointed at the old host; verify the sales-order service first because the morning autowave depends on it.
