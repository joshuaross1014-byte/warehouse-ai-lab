# 02 - Schema and SQL gotchas

Each item makes a syntactically valid query return wrong or empty results **with no error**, or breaks a deployment silently. Verified by executing against a production instance; re-check yours.

## Columns that were empty on every row

| Column | Reality on the instance studied | Use instead |
|---|---|---|
| `t_order.rush` | constant | `priority` |
| `t_receipt.vendor_code` | NULL | join `t_po_master` |
| `t_location.replenishment_location_id` | NULL | - |
| `t_location.stored_qty` | 0 or NULL, never maintained | `SUM(t_stored_item.actual_qty)` |
| `t_hu_master.parent_hu_id` | NULL (nesting unused) | - |
| `t_order.drop_ship` | NULL; never read or written by the import proc | - |
| `t_al_host_shipment_master.delivery_SAP` | NULL | the ERP's `U_HighJumpID = shipment_id` |
| `t_al_host_sql_export_queue.status` | always 'N' | `date_finished` on the interfaces that process |
| `t_work_q.employee_id` | NULL | `t_pick_detail.user_assigned` per line |
| `t_zone_loca.pick_seq` | '0' | `t_allocation.picking_flow` / `t_location.picking_flow` |
| `t_tran_metrics` | empty table | `t_tran_log` |
| `t_fwd_pick` | empty (no native dynamic replenishment) | explains why let-down lists are built by hand |
| `t_order.date_picked` | stays 1900-01-01 on flow-through orders even after ship | `t_pick_detail` / tran_log 301 |
| `t_pick_detail.container_id` | NULL on flow-through orders; staged picks link to the pallet via `load_id` | |

## Type and join traps

- `t_employee.employee_id` is **int**; `t_tran_log.employee_id` is **nvarchar(10)** and some ids are non-numeric. Join on `t_employee.id` (nvarchar). RF employee ids can also be device/fork ids with no employee row.
- `t_order.order_number` is nvarchar; the ERP document number is an integer. Cast when listing.
- Open picks mostly have **no** `t_allocation` row; an INNER JOIN drops most of them. PICKED/STAGED/SHIPPED/CLOSED lines have zero allocation rows; allocations exist only on RELEASED lines and are consumed inside the pick transaction.
- Collation `Latin1_General_BIN`: `Profile` and `PROFILE` are different values. Config FKs reject case variants. Check exact-case existence before loading config from another server.
- `t_item_master` grain is item x warehouse; `t_stored_item` grain is item x location x lot (x hu).
- SAP B1 `UpdateTS` is HHMMSS as an integer with leading zeros dropped (14029 = 01:40:29). `UpdateDate` is date-only.

## Time base

`t_tran_log.start_tran_date` is the date at midnight; `start_tran_time` / `end_tran_time` carry time-of-day on a **1900-01-01** base.

- `MIN/MAX(start_tran_time)` silently caps any span at 24 h.
- `end_tran_time < start_tran_time` yields pure false positives (midnight crossers).
- `elapsed_time` (seconds) is already correct across midnight. Trust it.
- Instant = `start_tran_date + CAST(start_tran_time AS datetime)`.
- Device clocks can be hours off server time; photo timestamps are not server time.
- Bulk corrections (one receiver keying a huge quantity) create spikes that ruin averages over that window.

## Hidden characters

A leading TAB in `t_stored_item.lot_number` (from a manual increment-inventory entry) made a row look identical in every UI while the web inline edit matched 0 rows and FEFO treated it as a different lot. When "edit does not save for one row but works for others", check `lot_number <> LTRIM(RTRIM(lot_number))` or `CAST(lot_number AS varbinary(8))` before suspecting permissions. Item descriptions can carry embedded CR.

## The MCP session transaction wrapper

A live-query MCP server typically opens a transaction per call and commits at the end.

- Vendor procs that commit internally (`usp_allocate`, `usp_af_release_wave`, `usp_afo_release_wave`) throw **error 266** on the first call; the work still commits. Prefix `IF @@TRANCOUNT>0 COMMIT;` when testing, or use an autocommit connection.
- **Any error anywhere in a batch rolls back an otherwise successful ALTER.** Run DDL alone; verify in a separate call.
- EXEC arguments cannot be `GETDATE()`; declare a variable.
- `SET NOEXEC ON` against the target compiles a deploy script and catches batch-level errors (duplicate DECLAREs, error 134) that dry runs miss.

## `sys.sql_modules` and ALTER text

`CREATE OR ALTER PROCEDURE` is stored as **`CREATE   PROCEDURE` with three spaces**; `ALTER`'d procs are stored back as `CREATE` with your spacing. A `REPLACE(..., 'CREATE PROCEDURE', ...)` misses it and the batch runs as CREATE (error 2714). Use `'ALTER ' + SUBSTRING(@sql, CHARINDEX('PROCEDURE', @sql), LEN(@sql))`. Rollback anchors and body hashes break on the same spacing.

When verifying guard order inside a proc, search from `CHARINDEX('BEGIN TRY', definition)` onward; header comments mention the same names and give the wrong answer.

`modify_date` can match on procs whose bodies differ (restores preserve it). Compare `HASHBYTES('SHA2_256', body from a stable anchor)` instead of dates.

## Catalog visibility traps

- `sys.server_principals` is restricted for non-sysadmin logins (returns only yourself + sa). A `LEFT JOIN sys.database_principals -> sys.server_principals ON sid` reports **false "orphaned user"** for service logins. Use `SUSER_SNAME(dp.sid)` or `SUSER_SID('login')`.
- `msdb` catalogs deny SELECT; use `sp_help_job` / `sp_help_jobschedule`. After editing a schedule, `@job_aspect='SCHEDULES'` keeps showing the old `next_run`; `@job_aspect='JOB'` is authoritative. Schedules can be **shared across jobs** (`job_count`): disable the job, never delete a shared schedule. `sp_add_jobschedule` with freq_type 8 requires `@freq_recurrence_factor = 1`. Non-sysadmins cannot modify jobs owned by another login (error 14525).
- The maintenance database's DDL event log would be the authoritative change history but SELECT is usually denied; `sys.objects.modify_date` is the fallback.
- `HAS_DBACCESS('REPOSITORY')` tells you whether design-database work is possible from a connection before you try.
- Passwords cannot be read from SQL Server; "confirm credentials" means the login exists, is enabled, is not locked, and the person signs in.

## Data shapes that mislead

- Open waves going back years are hygiene debris, not a daily signal. Filter on `created_date >= DATEADD(day,-3,GETDATE())` for actionable stuck waves.
- `COUNT(*) > 1` open waves per warehouse is normal; duplicate detection must group by the merge key (promised_date + ship_to_code + channel) at order level.
- "tran 321 with no matching 322" is **not** an abandoned-load detector: shipped LPs leave inventory and look identical. Confirm where the LPs actually are.
- `t_load_split_detail.destination` has the same format as `t_order.ship_to_code`; `t_appt_appointment_log.trailer_number` is hand-typed with typos. Never pattern-match trailer text.
- Stale never-waved status-N orders go back months (ERP re-export artifact); window on `promised_date`.
- Daily cross-dock departments can have zero `t_stored_item` rows; some items have no pick face at all (all bins type M).

## Writing a safe production fix

1. SELECT the exact rows with their count first; state the undo.
2. `SELECT * INTO dbo.bak_<topic>_<yyyymmdd> FROM ... WHERE ...` in the WMS database (REPOSITORY datawriter cannot create tables, so design-database backups also go there).
3. `BEGIN TRAN; <change>; <check @@ROWCOUNT>; COMMIT` with an abort when counts are off.
4. First line `-- project: NAME` so the memory bank's write ledger groups the rollout.
5. Read back from production; never from cache. Then refresh the memory bank's object versions if DDL was involved.
