# 05 - Receiving, inventory, RF sessions and devices

## RF session and device facts

- `t_device` is dead. Live gun state = `t_employee`: `device`, `wh_id`, `business_process`, `last_menu_item`, `last_tran_start_datetime` / `last_tran_end_datetime` (a start with no end = stuck session), `log_input_flag` ('N' for most users, so `t_emp_input_log` is empty).
- Logon history = `t_employee_logon` (tran 100, one row per logon: device, wh_id, location_id, start/end). Logins persist for days and roll at exactly 24 h.
- A gun's asset tag says nothing about its warehouse. Warehouse comes from the user's `t_employee.wh_id`.
- `t_employee.device` is stale metadata; `t_employee` can be a partial roster after a migration. Do not conclude "phantom user" from a missing row.
- RF `employee_id` in `t_tran_log` can be a device/fork id. To name a person, ask the supervisor who was on that truck.
- On "gun is stuck": query `t_employee` for user/device, `t_employee_logon` for device history, and `t_stored_item` of any type on the fork before concluding a receipt did not post.

## Receiving flow (`Receipt of Shipment` family)

- tran 153 receipt / 154 putaway; sub-processes Expiry, Quantity, TX, Putaway - Storage, Check Overage.
- Globals in `t_control`: `SINGLE_ITEM_LP`; `SHIP_ALLOCATE_INV` (if the flow reads a differently spelled key it resolves to 0, so Auto Reconcile is skipped and stock stays type SHIPMENT: `t_stored_item.type=-1`, `t_hu_master.type='IV'`, `control_number` = shipment until the web reconcile); `RECPT OVERAGE` (ceiling = PO qty); `LABEL_SOFTWARE`.
- Two over-receipt gates: `Check PO Qty Received` blocks an item once received >= PO qty; `Check Overage` on the qty screen.
- Expiry verification accepts slashed (8) and plain MMDDYY (6).
- Item expiry config per item+wh in `t_item_master`: `shelf_life`, `expiration_date_control`, `manual_expiry`, `lot_control`, `catch_weight`. Auto-fill items = `manual_expiry` N + shelf life; manual items = `manual_expiry` Y (blank first LP).
- Reverse-engineer any flow with a recursive CTE over `t_app_process_object_detail` resolving names per `action_type` (reference 07).

## Reconcile guards (customisations worth having in `usp_rcpt_ship_reconcile`)

1. **BOL upload gate** (per-warehouse switch): block reconcile unless an image row exists for wh+shipment with `DATALENGTH(image) > 0`. Before enabling a warehouse, confirm it is actually uploading; status-O shipments with no image are blocked at reconcile.
2. **Serial-completeness guard**: block "Reconcile All Items" when a serial-managed item (`serial_control <> 'N'`) has a staged pallet where `COUNT(t_serial_number by sto_id) <> actual_qty`, naming item + LPN. Fixes the interrupted-serial-scan pallet (0 serials, 1900-01-01 expiry) that strands inventory and blocks the ERP GRPO/Delivery. Pair it with a detection monitor.

Do not confuse an inbound BOL-upload gate with `SHIP_BY_DEST_BOL` (outbound printing; `c1` printer, `c2` report; its `next_value` is read by nothing in the vendor print proc).

## Catch-weight barcodes ("INVALID CW CONFIG")

A site barcode parser proc reads a config table keyed on item + packer code: `packer_code = LEFT(barcode, gtin_length)`, weight = `SUBSTRING(int_start,int_len) + '.' + SUBSTRING(dec_start,dec_len)`, pack date / serial by absolute position. No row = INVALID CW CONFIG. Fix = one config row per item (each item's own GTIN as packer code); validate by executing the parser with a real barcode. Data config, immediate, no compile.

## Staging-location pathologies

- **Item-managed staging** (`item_hu_indicator='I'`): flow-through receiving is LP-less. If a pallet receiver receives such a PO on the LP-building path, the staged stock carries an LPN and the picking flow loops on the same item forever. Diagnose by fork on the receipt date (LP-less fork: `t_receipt.hu_id` NULL on every line). Fix in reference 06.
- **Template-token LPs** (literal `{{equipment}}`): an unresolved InMotion / Enhanced-RF data-binding token in a shared receiving dialog passes the literal string as the equipment id; in fork-based putaway the destination LP becomes that value. The token exists nowhere in the databases; the fix is client-side (screen config). Monitor `t_stored_item.hu_id LIKE '{{%'`.
- **Outbound pallets in receiving staging**: 321 loads staging -> fork, 322 never happens, hours later the operator runs Receipt of Shipment to clear the fork, `DEF_STG_LOC_PUTAWAY` sends them to receiving staging **and re-types the HU from SO to IV**. An IV pallet is invisible to Load by Destination (`Find HUM w/Appt` requires `hum.type='SO'`) and manual scans fail "Err: Wrong HU Type". Detection: `t_hu_master WHERE hu_id LIKE '<DLP prefix>%' AND type='IV'` (type LO is legitimate). Repair in reference 06. Move put-away rejects SO LPs by design; never tell an operator to clear SO pallets via Move.
- `usp_move_lp` landmines: sets `parent_hu_id = @in_vchMasterHUID` unconditionally (pass the current parent), its HUM update is keyed on `location_id = @in_vchSourceLocationID` and silently no-ops when `t_hu_master` and `t_stored_item` disagree, and it writes **no `t_tran_log` row**. It deletes RELEASED/unassigned allocations pinned to the source and queues re-allocation.

## Location Full flag

`t_location.status='F'` is **not sticky**: every pick runs `Picking - TX` -> `Update Location Statuses` -> `usp_util_get_loc_full_flag` = 1 when `COUNT(DISTINCT hu_id) >= capacity_qty` (types I/M/P). Pick bins with capacity 1-2 pallets are correctly F while holding their resident pallet ("no room for another pallet"). Do not patch `usp_picking_tx` to flip it; the flow recompute overrides it immediately. The genuinely wrong bins = F with HUs < capacity_qty, stranded by paths that bypass the recompute (`usp_move_lp`, `usp_inventory_adjust`, DB fixes). Auto-heal them with the vendor recompute after a quiet period and no inbound reservation. If the floor wants putaway to target partially empty pick faces, that is a `capacity_qty` config decision.

## Held stock and the Move guard

A loose-quantity Move pick of status-H stock runs `usp_inventory_adjust` -> `usp_hold_adjust`, which can fail to carry the hold (source row deleted on full pick; a lot-number parameter narrower than real lots) and deletes the orphan: held stock with no `t_holds` row, invisible to release. Fix: in the `Move` flow, change the `Err: Item On Hold` step's pass label so loose picks of held stock are refused while the whole-LP path stays. Operator note: held stock moves whole-LP or after QC release.

## Reset device and stranded batches

- The console "Active Devices" reset and the RF reset both call the customer-owned `usp_reset_device_picking`. Worth hardening: drop all fork inventory (pick-linked via `usp_pk_drop`, non-pick LPs via `usp_move_lp`), always clear the login lock, per-item resilience, remove label-printer coupling, log 070, and **release the worker slot** (find 'A' batches with RELEASED remainder where `t_pick_detail.user_assigned` = the reset employee -> `t_work_q` status U, `workers_assigned - 1`).
- Stranded multi-order batch symptom: "NO WORK IS AVAILABLE" on every scanner while lines are RELEASED and allocated. Dispatch requires `workers_assigned < workers_required`. Manual remedy: `UPDATE t_work_q SET work_status='U', workers_assigned = workers_assigned - 1` **only after the supervisor confirms nobody is on it**; a slot that looks stranded can be a live picker. Separate genuinely unallocatable lines from the assignment problem first; they look the same on the gun.
- The Reset Device web page's pick-list SQL may hardcode a warehouse and lack an ORDER BY; fix in the page editor with the warehouse token and an ORDER BY that puts outbound staging first.

## Foreign-character "SQL Failed" on RF

Most items already have non-ASCII descriptions and scan fine; the crash is usually two defects in a list statement: (A) `RIGHT(item_number,4)+'-'+description` overflows a byte-sized RF field when multi-byte UTF-8 pushes it past the field length; (B) the sequence field is 2 chars with no `TOP 99`. Fix = a scalar function that maps CR/LF/TAB to space, strips non-printable ASCII, collapses spaces and caps length, exposed through a view, with the list statements re-pointed to the view; leave `t_item_master.description` untouched so web/labels/ERP keep the original text. CRLF vs LF matters in anchored REPLACEs.

## Expiry dates are receiving artifacts

Default-dated receipts (receipt + shelf life) make FEFO ~= FIFO; receipts keyed with receipt + 1 day (one receiver login, or `shelf_life=1` masters) produce "expired" stock on pallets and in pick slots that is a labeling artifact, not spoilage. Always pair a FEFO compliance claim with a receipt-order check (lot prefix = receipt date) and a receiving shelf-days audit; recommend an RF warn when expiry < N days from receipt and a shelf-life master cleanup.

## Sticky expiry (design-database change)

A DB action returning the first LP's expiration for shipment + item as an **MMDDYY string into a string dialog field** lets later LPs of the same item default to the first LP's date. Returning a datetime into the date field stamps a `/ /` picture on the prompt and regresses it.
