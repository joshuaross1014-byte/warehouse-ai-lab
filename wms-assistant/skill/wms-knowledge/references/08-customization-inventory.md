# 08 - Customization inventory: what exists, what survives a restore

This file is a **template plus the queries that fill it**. In the private version it holds a dated live snapshot of production; refresh it before any cutover and never trust it unrefreshed.

## The governing rule

A database restore carries **only what lives inside that database**: procs, tables, views, functions, `t_whse_control` rows, data. It does **not** carry SQL Agent jobs (msdb), design-database work (RF flows, statements, fields), web-page SQL stored in config files, or anything on workstations (monitors, MCP servers, indexes). Before any move: full `sys.objects` diff between the two servers, capture every delta idempotently, confirm with the vendor whether msdb is replaced.

## A. Custom objects inside the WMS database (survive a copy; verify, do not rebuild)

| Object | Type | Modified | Purpose / notes | Re-apply kit |
|---|---|---|---|---|
| `<autowave proc per department>` | proc | | second-run merge, transfers 1-per-wave, channels | `<kit path>` |
| `<autorelease proc per department>` | proc | | priority order, current-cycle filter, Workers=1 default | |
| `<priority table>` (+ dated backups) | table | | wh_id, ship_to_code, priority, active, note | |
| `usp_rcpt_ship_reconcile` | proc | | BOL gate + serial-completeness guard | rollback script |
| `usp_reset_device_picking` | proc | | hardened + work-queue release | hash-gated deploy + byte-exact rollback |
| `usp_ship_by_dest_print_bol` | proc | | print-suppression guards | |
| `usp_af_assign_pick_locations`, `usp_allocate` (+ `_bkup_<date>`) | procs | | order-type allocation overrides | re-derive script that aborts on anchor drift |
| `<LEFO rule procs>` + `t_pick_put_rules/master/detail` rows | procs, config | | | |
| `usp_PkBestQtyFEFO` | proc | | in-house FEFO customisations | |
| `usp_al_import_order` | proc | | importer edits | |
| `<RF-safe description function + view>` | fn, view | | foreign-character fix | |
| `<orphan-pick janitor + log tables>` | proc, tables | | **dormant; jobs deleted; preview default 1; do not schedule** | |
| `<flow-through receiving table + procs>` | table, procs | | web-page backend | |
| barcode parser procs + config tables | | | catch-weight / GS1 | |
| `*_bkup_*`, `zz_*`, `bak_*` | backups | | design-database backups live here because REPOSITORY datawriter cannot create tables | |

## B. `t_whse_control` switch matrix (template)

| control_type | WH1 | WH2 | ... | Meaning | Rollback |
|---|---|---|---|---|---|
| autowave enable (per department) | | | | | `next_value=0` |
| autowave transfer / channel flags | | | | | |
| autorelease enable / priority / cycle | | | | | |
| `AUTO_WAVE_GEN` (c2 prefix) | | | | wave id seed | |
| BOL upload gate | | | | inbound reconcile gate | |
| BOL print suppression | | | | also kills the manual reprint page | |
| `SHIP_BY_DEST_BOL` (c1 printer, c2 report) | | | | `next_value` is dead; never "fix" the proc to honour it | |
| LEFO switch (c1 profile) | | | | needs a transfer-order-type row | |
| bulk-pick skip key | | | | | |
| market order type / staging location | | | | | |
| `DEF_STG_LOC_PUTAWAY` (c1) | | | | why abandoned fork loads land in receiving staging | |

`control_type` is NVARCHAR(20). Design every feature so rollback = set `next_value` back to 0.

## C. SQL Agent jobs (msdb; never survive a database restore)

List every enabled TSQL job with owner, schedule, shared-schedule ids and the proc it runs. Have custom jobs owned by `sa`, not a developer login (a disabled login takes its jobs down). Job-name mismatches between servers cause duplicates on import. Keep a job-recreation script, and remove from it any job you have since deleted on purpose.

## D. Design-database changes (erased by any platform upgrade or REPOSITORY restore; re-apply then compile + activate)

| Change | Objects | Since | Re-apply |
|---|---|---|---|
| foreign-character fix + list ordering | N statement patches, list objects, view | | idempotent script with CRLF-aware anchors + rollback |
| bulk-pick skip key | flow vN, cloned LP screen, finder vN, session field, soft-key resource | | atomic deploy with a final THROW check |
| Move hold guard | `Move` vN step pass-label | | staging script that THROWs unless the expected version is current and unlocked |
| vendor work in progress | objects without VC rows | | vendor's |

Keep a separate list of TEST-only changes so nobody assumes they are live.

## E. Outside the databases (nothing about a database migration preserves these)

MCP server host settings; scheduled monitors (run only while the owning user is logged on; move them to a server with a service account); caches (memory bank, document index, dependency graph: refresh after schema/proc changes); comparison and report scripts; runbooks and the issue log.

## Refresh queries

```sql
-- A. custom objects (adapt the suffix/prefix patterns to your naming convention)
SELECT name, type_desc, create_date, modify_date FROM sys.objects WITH (NOLOCK)
WHERE is_ms_shipped = 0 AND (name LIKE '%\_<site_suffix>' ESCAPE '\' OR name LIKE '<custom_prefix>%'
   OR name LIKE '%\_bkup\_%' ESCAPE '\' OR name LIKE 'zz_%' OR name LIKE 'bak\_%' ESCAPE '\')
ORDER BY type_desc, name;

-- B. switches
SELECT control_type, wh_id, next_value, c1, c2 FROM dbo.t_whse_control WITH (NOLOCK)
WHERE control_type LIKE 'AUTO%' OR control_type LIKE '%BOL%' OR control_type IN ('<your custom switches>')
ORDER BY control_type, wh_id;

-- C. jobs (sp_help_job works for non-sysadmins; sysjobs does not)
EXEC msdb.dbo.sp_help_job @subsystem = N'TSQL', @enabled = 1;

-- D. REPOSITORY: check-outs and label ceilings
SELECT name, version, locked_by FROM REPOSITORY.dbo.t_app_process_object WITH (NOLOCK) WHERE locked_by IS NOT NULL;
SELECT id, version, COUNT(*) AS labels FROM REPOSITORY.dbo.t_app_process_object_detail WITH (NOLOCK)
WHERE label <> '' GROUP BY id, version HAVING COUNT(*) > 37;

-- E. body hash for drift (dates lie after a restore)
SELECT OBJECT_NAME(object_id) AS name,
       CONVERT(varchar(16), HASHBYTES('SHA2_256', SUBSTRING(definition, CHARINDEX('BEGIN', definition), 100000)), 2) AS body_hash
FROM sys.sql_modules WHERE OBJECT_NAME(object_id) IN ('<proc1>', '<proc2>');
```
