# 01 - Environment, codes and key tables

Vendor-standard names are real; site values are placeholders. Fill the tables in for your instance and date them.

## Platform

- Product: Körber (formerly HighJump / Accellos, now Infios) **Warehouse Advantage**. SQL Server; collation **Latin1_General_BIN (case-sensitive)** on the instance this was learned on.
- One WMS database typically serves **several warehouses** and can serve **several ERP companies** (`t_order.warehouse_owner`). Code, allocation engine and config tables are shared; behaviour differs only through `t_whse_control` rows and data.
- RF guns run Advantage Architect "process objects" (flows) compiled from the **REPOSITORY** design database. Web UI = WebWise (page SQL lives in `.wdb` config files on the web servers) plus the Körber One / HJ One console (`KoerberOneCore` database).

## Environment map (template)

| Env | Role | Host |
|---|---|---|
| PROD | SQL instance (WMS db, ADV, ARCH, AUD, maintenance db, KoerberOneCore, REPOSITORY, Report) | `<PROD_SQL_HOST>` |
| PROD | Application / Architect compile server (compiler error file `ADV.ERR` under `ProgramData\Koerber\Compile\<app>\`) | `<PROD_APP_HOST>` |
| PROD | WebWise web server (`.wdb` configs under `ProgramData\Koerber\Web Configs\`) | `<PROD_WEB_HOST>` |
| PROD | SSRS; Telnet for RF guns (port 4400) | `<PROD_SRS_HOST>`, `<PROD_TEL_HOST>` |
| TEST | same five roles | `<TEST_*_HOST>` |

Rule that saves incidents: name the environment by **host**, not by registration alias. A query result that reports the production host is production whatever the connection was called.

## Warehouses and wave-id prefixes (template)

Wave id = prefix + MMDDYY + "-" + sequence, driven by `t_whse_control AUTO_WAVE_GEN` (prefix in `c2`, last date in `c1`, next sequence in `next_value`). Autowave channel waves may carry a suffix.

| wh_id | Prefix | ERP company | Notes |
|---|---|---|---|
| `<WH_1>` | `<NNN>` | `<COMPANY>` | which automations are on |
| ... | | | |

ERP `RDR1.WhsCode` equals the WMS `wh_id` one-to-one on the HighJump add-on; transfer destinations are separate "staging-in" warehouse codes. Non-WMS ERP warehouses (3PL, drop-ship) never appear in the WMS even when flagged for export.

## Order types (`t_lookup`, source t_order)

| type_id | Text (as in `t_al_host_order_master.order_type`) | Notes |
|---|---|---|
| 31 | Sales Orders | store/customer orders |
| 32 | Transfer Orders | ERP inventory transfer requests |
| 632 | Crossdock Orders | gates the cross-dock ASN procs |
| 634 | Return to Vendor | |
| `<custom>` | e.g. a market/flow-through outbound type | picks from an inbound staging location; the matching **PO** type is a different id |

The item cross-dock profile (`t_item_master.xdock_profile_id`) had zero code consumers on the instance studied; it does not control cross-dock or flow-through behaviour.

## Status codes

| Table.column | Values |
|---|---|
| `t_order.status` | **N** new/open, **B** waved (also "closed" by Cancel), **S** shipped (set at ship-confirm regardless of fill rate; Cancel sets S if any pick shipped), **D** done/picked-staged, **I** |
| `t_wave_master.status` | **N** new, **H** hold, **A** allocating, **R** released, **W**, **E** |
| `t_pick_detail.status` | words: RELEASED, PICKED, STAGED, LOADED, SHIPPED, CLOSED |
| `t_stored_item.status` | **A** available, **H** hold (needs a `t_holds` row), **U** unavailable (physical count creates U; nobody releases it) |
| `t_stored_item.type` | 0 normal, **-1 transient post-receipt** (before the shipment step confirms), bigint NOT NULL |
| `t_location.type` | **P** pick face, **M** reserve/bulk, **S** staging, F, D, X cross-dock, I |
| `t_location.status` | **F** full (recomputed per pick: distinct HUs >= capacity_qty), **E** empty, **P** partial, **I** inactive |
| `t_location.item_hu_indicator` | **H** HU/LP-managed, **I** item-managed |
| `t_hu_master.type` | **IV** inventory, **SO** staged outbound (loadable), **LO** loaded on a dock door (legitimate), **RC** receiving |
| `t_al_host_*.import_status` | NULL pending, **I** in progress, **S** success, **E** rejected/error |
| `t_al_host_order_master.processing_code` | NEW, UPDATE, Delete |
| `t_rcpt_ship.status` | **O** received not reconciled, **R** reconciled |
| `t_work_q.work_status` | **U** unassigned/open, **A** assigned, **C** complete |
| `t_al_host_sql_export_queue.status` | always 'N' on the instance studied; judge outbound health on `date_finished` of the interfaces that actually process |

## tran_type (`t_tran_log`)

| Code | Meaning |
|---|---|
| 070 | Reset device / admin inventory move |
| 100 | Logon (`t_employee_logon`) |
| 153 / 154 / 156 | Receipt of Shipment (Rcpt / Put / confirm). 153 is written at **confirm**, not at scan |
| 201 / 202 | Move pick / put (putaway) |
| 211 / 212 | Directed pickup pick / put (replenishment) |
| 301 / 302 | Picking pick / put (302 carries no tran_group_id; cannot be paired to 301 that way) |
| 321 / 322 | Loading pick (staging -> fork) / put (fork -> dock) |
| 324 | Unload |
| 341 | Shipping detail (ship confirm) |
| 391 / 392 | Unpick |
| 542 / 543 | Decrement / increment inventory (manual) |
| 880 | Physical inventory / count (creates status U stock) |
| 950 | Cancel Outbound Order (`usp_ww_cancel_order`) |

Productivity mapping (one leg per task): PICK 301+211, PUTAWAY 154+212, LOAD_SHIP 321+341, MOVE 201, RECEIVE 153, CYCLE_COUNT 880. `t_tran_metrics` was empty; use `t_tran_log`.

## Key tables by area

- **Orders**: `t_order` (wh_id + order_number; `load_id`; `ship_to_code`; address denormalised; `bill_to_code`/`customer_id` NULL on the HighJump feed; `drop_ship` unused), `t_order_detail` (`afo_plan_qty`, `qty_shipped`, `warehouse_owner`), `t_order_comment`.
- **Host staging** (`t_al_host_*`): `_order_master/_detail`, `_po_master/_detail`, `_item_master/_uom/_upc`, `_receipt`, `_shipment_master`, `_sql_import_queue`, `_sql_export_queue`, `_import_log`, `_resubmit_log`, `_order_status`.
- **Waves**: `t_wave_master`, `t_afo_wave_detail` (+`_line`) = the autowave "recipe" that regenerates picks (hold/delete do not clear it).
- **Picks**: `t_pick_detail` (planned/picked/staged/loaded/shipped quantities; `user_assigned`; `work_q_id`; `staging_location`), `t_allocation` (pick_id, pick_location, lot, quantity, `picking_flow`; transient, deleted as picked; exists only on RELEASED picks), `t_allocation_q` (U queued / C done), `t_work_q` (`workers_required`, `workers_assigned`; `employee_id` always NULL), `t_work_q_assignment`.
- **Inventory**: `t_stored_item` (sto_id identity bigint; item x location x lot x hu; `actual_qty`, `unavailable_qty`, `fifo_date`, `expiration_date`, `shipment_number`, `control_number`), `t_hu_master` (hu_id = LPN; `type`; `load_id`; `parent_hu_id` unused), `t_serial_number` (keyed by `sto_id`), `t_holds`, `t_location` (`capacity_qty`, `picking_flow` 3-char path code, `stored_qty` never populated), `t_pick_area`, `t_zone_loca` (`pick_seq` useless).
- **Receiving**: `t_rcpt_ship` -> `t_rcpt_ship_po` -> `t_rcpt_ship_po_detail` (`received_qty` owned by reconcile), `t_receipt` (`vendor_code` NULL; reach vendor via `t_po_master`), `t_po_master` / `t_po_detail`.
- **Shipping**: `t_load_split_detail` (`destination` = ship_to_code, `appointment_id`), `t_appt_destination_detail`, `t_appt_appointment_log` (free-text trailer), `t_ob_door_status`.
- **Items**: `t_item_master` (item_number + wh_id grain; `serial_control` 'F'/'N'; `lot_control`; `catch_weight`; `expiration_date_control`, `manual_expiry`, `shelf_life`; `pick_put_id`; `item_department`), `t_item_uom` (`pick_put_id`), `t_item_upc`, `t_item_vendor`.
- **People / devices**: `t_employee` (`id` nvarchar is the join key; `employee_id` int; `device`, `wh_id`, `last_tran_start_datetime`/`_end_datetime`), `t_employee_logon`, `t_emp_input_log`. RF `employee_id` values in tran_log can be devices/forks, not people.
- **Config**: `t_whse_control` (per wh; `control_type` NVARCHAR(20) so names must be <= 20 chars; `next_value`, `c1`, `c2`), `t_control` (global), `t_lookup`, `t_pick_put_master/_detail/_rules`, `t_menu` (one tree for all whs, keyed by menu_level), `t_intlv_process`, `t_intlv_gp_master/_detail`, `t_sm_alert_configuration`.

## Staging locations (roles)

| Role | Behaviour |
|---|---|
| Receiving staging (`DEF_STG_LOC_PUTAWAY`) | default putaway target; where abandoned fork loads end up when cleared via the receiving flow |
| Inbound / flow-through staging | item-managed; LP-less receiving; picks source here with `picking_flow='000'` |
| Outbound staging | `t_pick_detail.staging_location`; loading source (321); HU-managed; staged pallets are type SO |
| Dock doors | loaded (322) pallets, type LO |
| Fork / equipment locations | stock sitting here is on a fork |

## Other databases on the instance

- `REPOSITORY`: Architect design (99 tables incl. the `t_app_*` / `t_act_*` families). Needs read for reverse-engineering and write for raw-SQL development.
- `KoerberOneCore`: HJ One console + mobile app model (`MobileApplication`, `MobileScreen`, `PageMetadata`, `Resource` blobs). WebWise page SQL is **not** here.
- Maintenance database: DDL-trigger target table. Anyone given db_owner on the WMS database without INSERT on that table has every CREATE/ALTER PROC fail.
- `msdb`: Agent jobs. Non-sysadmin logins manage only jobs they own via `sp_add_job`/`sp_help_job`; direct SELECT on `sysjobs` is denied.
