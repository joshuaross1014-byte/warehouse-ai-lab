# 04 - Allocation, waves, autowave and autorelease

## Wave lifecycle

1. Wave created (manual UI, or an autowave job) -> `t_wave_master` N, `t_afo_wave_detail` (+`_line`) = the recipe of orders/lines (`t_order_detail.afo_plan_qty > 0` is required or the recipe is silently empty).
2. Release (`usp_afo_release_wave` publishes async; `usp_af_release_wave` enqueues directly -> wave A) -> allocation service drains `t_allocation_q` (U -> C within seconds) -> `t_pick_detail` RELEASED + `t_allocation` rows + `t_work_q` -> wave R. **Allocation happens at release, not creation.** Released-unallocated picks are back-filled by the allocation queue when stock lands.
3. RF picking: flows only offer picks that have a `t_allocation` row. 301 pick -> fork, 302 drop -> STAGED at outbound staging, pallet minted via the `DLP_GENERATION` control.
4. Loading 321/322 (needs `t_hu_master.type='SO'`, a `t_load_split_detail` row with `appointment_id IS NULL`, destination matching `t_appt_destination_detail.store_id`), ship 341 (`usp_ship_by_dest_tx` has no `t_order.status` gate), BOL print via `usp_ship_by_dest_print_bol`.
5. Ship-confirm sets `t_order.status='S'` **regardless of fill rate**. Nothing native closes leftover RELEASED picks (see orphan picks in reference 06).

Hold (`usp_afo_hold_wave`) deletes picks, frees allocations, clears work_q/labels/containers, sets H. It and `usp_afo_unbuild_wave_data` **throw "Picking has started"** whenever any pick has picked/staged/loaded qty > 0. `usp_delete_wave` deletes only the `t_wave_master` header (returns 'NONE' on success). Neither touches `t_afo_wave_detail`. Hold also fires ship-void/cartonization if `MANIFEST_SYSTEM`, `HJSHIP_INSTALLED` or `CONTAINER-OPTIMIZE` are on for the warehouse.

## Allocation engine

Profile resolution happens per pick in **two engines**: `usp_af_assign_pick_locations` (wave release; also the natural place for order-type overrides at label `NO_OVERRIDE:`) and `usp_allocate` (re-allocation). `usp_during_pick_best_loc` (RF short-pick re-pick) has **no** order override. Profile = `ISNULL(usf_get_item_ppr_dia_ovrd(...), itu.pick_put_id)`; `pick_put_id` is item-level (`t_item_master` / `t_item_uom`).

Granularity = **location + lot**. The rules never choose LPs; multi-LP splits at a bulk location are RF-level LP direction. Lots "mix" across orders when they share an expiration **date**. Eligibility = INNER JOIN to `t_pick_area` (locations with no registered pick area are invisible regardless of type), `loc.status<>'I'`, `sto.status='A'`, `sto.type=0`, net qty = actual - unavailable - SUM(t_allocation per location+lot) > 0.

A profile cascades rules, each returning one location+lot+qty with the remainder cascading:

| Rule proc | Behaviour |
|---|---|
| `usp_PkBestQtyFEFO` (commonly customised) | location types XPASMI; a **hard FEFO date gate** (only stock with the single soonest expiration date is considered); full-coverage ranking then a fallback. Site customisations seen: serial items skip it, lower rack level first, least surplus, biggest-pile fallback |
| `usp_PkFEFOLstQty` (vendor) | strict `ORDER BY expiration_date, type, user_count, net qty ASC` (pick-to-clean smallest first) |
| `usp_PkFEFOBestQty` (vendor) | expiry first, full coverage preferred then least qty |
| LEFO variants | the same shapes with the date gate flipped to **latest** expiration, useful for transfers to other DCs while store orders keep FEFO; gated by a per-warehouse `t_whse_control` switch and the presence of a transfer-order-type row |

Latent defect to design around: in a wave mixing two order types for the same item, the vendor wave-quantity allocation resolves one profile from the lowest pick_id and spreads it across all picks of that item. Keep single-type waves or add a guard.

Allocation diagnostics: write a candidate-ranking replica of the rule (same eligibility joins, same ORDER BY) and compare to `t_allocation` for a sample pick. Pick/put rule tables `t_wl_*`, `t_afo_control`, `t_pick_pass_sequence`, `t_pick_task_uom` were empty on the instance studied.

## Why picks go short (a produce study)

Engine and config were identical across warehouses; differences were operational. One warehouse ran a single autowave burst per day with a human releasing waves in a fixed order 20 minutes later, so the last store always ate the shorts; another created waves rolling all day. Shorts on a bad day: mostly vendor no-shows, then receiving after the burst (recovered next day), then stock in the building but blocked (QC holds, status U from counts). Status-U stock from physical counts is never released to A by anyone unless someone owns count approval.

## Pick splits ("same item picked 2-3 times on one LP")

Stock behaviour: `Picking - TX` -> **Post Pick Checks** runs `List PKD Split w/User, Type, Itm` (0 < picked < planned for this user+item), inserts a new `t_pick_detail` row for the remainder (`create_date` milliseconds after the 301 end time, `prev_pick_id` NULL), updates planned qty and `t_allocation.pick_id`, loops to item select. Triggers: LP ran out (default qty capped at the LP's quantity), allocation spans lots/locations, or the operator confirmed fewer than shown. Not an allocation shortage.

## Autowave and autorelease (custom job pattern)

A per-department autowave proc parameterised by `@in_wh_id`, scheduled by SQL Agent, plus an autorelease proc. Design lessons:

- Merge key = promised_date + ship_to_code + channel. Decide explicitly which channels collapse ship_to (flow-through orders into one wave) and which split per ship-to; document the decision so the rule sheet and the code agree.
- **Second-run merge**: a later run appends new orders to an existing open N/H wave of the same key within the proc's department domain instead of minting a duplicate. Add a release-race guard: if the matched wave leaves N/H between detection and attach, allocate a fresh wave. When adding a gated feature to a proc shared by several warehouses, the gate must also cover clauses that read **existing** wave state, not just the new-order pull.
- Weekend day logic (which promised date a Saturday run targets) belongs in one place and in the autorelease's current-cycle filter too.
- Transfer orders: **one transfer order = one wave**, never merged.
- Autorelease: release current-cycle waves in **store-priority order** from a priority table (wh_id, ship_to_code, priority, active, note), pass the priority to `usp_afo_release_wave`; unlisted ship-tos sort last and get the job-step fallback priority. Declare `@in_nWorkersRequired = 1` in the proc **and** pass it explicitly from the job step: a 0 flows to `t_work_q.workers_required=0` and operators must fix every wave by hand. Log a SUMMARY row per run.
- First enable of autorelease on a warehouse sweeps **all** lingering status-N waves of that department; clean old N waves first.
- Per-warehouse switches in `t_whse_control` (names <= 20 chars): enable, transfers, special channels, priority ordering, current-cycle filter. Flags off = exact pre-feature behaviour, which makes rollback one UPDATE.
- SQL Agent: job names must match across environments or an import creates duplicates; schedules can be shared between jobs (disable the job, never delete the schedule); have jobs owned by `sa`, not a developer login.
- Reload of the priority list: parse the spreadsheet, validate, **FULL OUTER JOIN against the table to see the diff before writing**, back up with `SELECT INTO`, write priority as a string.

## Flow-through (market) picking

- Config per warehouse: a market order-type control, a staging-location control, `MIX ORDER TYPES=0`, a single-UOM prompt. One order per store; one wave spans many stores. Flow = inbound staging (receive, LP-less, generated lot) -> sort by store -> outbound staging (pallet type SO) -> dock.
- A simplified two-screen RF path for batch items is a design-database change gated by a `t_whse_control` switch; keep serialized items on the full flow.
- Pathologies: orphan STAGED picks colliding next day, LPN on item-managed stock looping the gun, outbound pallets received into receiving staging (reference 06).

## RF list ordering and a "skip item" key

- Receiving F8 list: order by **PO line number** (`MIN(TRY_CONVERT(int, pod.line_number)), item`), `TOP 99`, descriptions through an ASCII-safe view.
- Picking F8 list: order by **pick flow** (`MIN(alo.picking_flow), display_item_number`) so the next item on the list is the next bin on the path. The list is driven by `t_work_q_assignment` (user + fork zone + pick area), not wave_id; test rigs insert a temporary assignment row. TOP 99 means a large wave shows the nearest 99.
- A bulk-pick "skip for now" soft key: a cloned LP screen appends the item to a session field (8000 chars), the shared finder sorts bypassed items last, the list is cleared at wave entry, F1 exit and wave end; allocation untouched. Gate it per warehouse; note the flag is read once per wave.

## Replenishment let-downs

`t_fwd_pick` empty means no native min/max replenishment. Simulate allocation read-only: demand = N orders in a promised_date window not on an active wave; supply = type-P stock net of allocations; shortfall sourced from type-M bins by fifo_date; print per-zone sheets. Full-pallet bulk picks from reserve when the pick face has stock are the known fidelity gap.
