# Advantage RF object model — reverse-engineered

How the Körber/HighJump Advantage RF application stores its design, so objects can be authored in raw SQL and cloned reliably. Object names are the vendor's standard schema; GUIDs below are illustrative placeholders.

## Design vs. runtime

- **Runtime DB** — operational data: RF menus (`t_menu`), employees, inventory, transactions. The RF client reads compiled output here.
- **Design DB (the Architect repository)** — every field, dialog, screen, process, and DB action lives here. Editing happens here; then **Compile + Activate** (GUI only) publishes it to the runtime.

## Menu → process → actions

- **RF menu:** `t_menu` (runtime), where `process` = a process object's name. Visibility is gated by named `menu_level` sets matched to the employee's `menu_level`.
- **Process object:** `t_app_process_object` (+ `_detail` = the ordered steps). Each step's `action` code and `action_type` together resolve the target action:

| Step type | action | action_type | action_id points to |
|---|---|---|---|
| DB action | 4 | 5 | `t_act_database.id` |
| Dialog (screen) | 5 | 6 | `t_act_dialog.id` (header) |
| Subprocess | 2 | 1 | `t_app_process_object.id` |
| Terminator | 13 | -1 | literal `PASS` / `FAIL` |

`action_type` catalog: **1**=subprocess, **3**=`t_act_calculate`, **4**=`t_act_compare`, **5**=`t_act_database`, **6**=`t_act_dialog`, **7**=`t_act_execute` (calls a .NET assembly method), **13**=`t_act_send`.

**Flow control:** each step names the next via `pass_label` / `fail_label` (matched to another step's `label`); terminators return `PASS`/`FAIL` to the caller. A typical linear flow: `PROMPT → DB → DIALOG → DB → DIALOG → DONE(PASS) / ERR(FAIL)`.

- **DB action** (calls a stored proc): `t_act_database` (+ `_detail.statement`), where the statement is `STATEMENT( … EXEC proc :#17#<fieldGUID>#: … SELECT cols )RETURNS(:#17#<fieldGUID>#:)`. `:#17#` injects a field's value; SELECT columns map positionally into the RETURNS fields.
- **Field:** `t_app_field`.
- **Dialog** (a complete one needs all of): header `t_act_dialog` + **`t_act_dialog_detail`** (the field binding — the piece most easily missed) + `t_act_dialog_ref` (one per screen group) + `t_act_dialog_ref_detail` (→ `t_app_screen_format`).

## The clone-with-substitution rule (mandatory for every object)

Each design object must be written across **four coordinated tables** or the Architect/compiler won't see it:

1. the **main** row (e.g. `t_app_field`),
2. its **`_h`** history row (keyed by `version_control_id`),
3. a **`t_app_version_control`** row (`object_type`: 17=field, 5=DB action, 6=dialog, 26=screen, 1=process),
4. a **`t_app_revision`** row it points to.

Build new objects by copying a known-good object's rows across all four tables and changing only id/name/length/statement. **Attribute the work** by creating your own `t_app_revision` (`changed_by`/`developers`) and referencing its id in every `t_app_version_control.revision_id` — don't reuse someone else's historical revision.

### Version-control anatomy

`t_app_version_control` columns: `id` (the version_control_id), `object_type`, `object_id` (the object's own id), `version`, `action`, `label_sequence`, `revision_id`. The `_h` history rows are keyed by `version_control_id`. **One vc row per sub-part** — so a dialog needs the header + `t_act_dialog_detail` + N refs + N ref-details all accounted for. A short count means a sub-row is missing.

### Screen / dialog anatomy

- **Screens** (`t_app_screen_format` + `_detail`): one screen per device size (screen groups). Detail rows: `data_usage` 1=input / 3=display, `data_type` 17=field, `data_id`=field id.
- **Dialog** top-down: `t_act_dialog` → `t_act_dialog_detail` (`input_type` 1, `field_type` 17, `field_id`, `prompt_type` 17, `prompt_id`) → `t_act_dialog_ref` (per screen group) → `t_act_dialog_ref_detail` (→ `screen_format_id`).

## Compile + Activate (the only manual step)

After inserting raw objects: **Run → Compile Application** (production compile, checked-in objects) → if 0 errors, **Activate**. Compile errors are specific and DB-fixable, so the loop is: insert → compile → read error → fix in SQL → recompile.

## Debugging technique — find a missing companion row

When Compile reports an object "could not be found" even though its main row exists, the cause is almost always a **missing child-table row**. Scan every string column in the design DB for a **known-good** object id vs. the **broken** one — whichever table has the good id but not the broken id is the missing row:

```sql
DECLARE @good varchar(40) = '<known-good-object-id>';
DECLARE @bad  varchar(40) = '<broken-object-id>';
DECLARE @sql nvarchar(max) = '';
SELECT @sql = @sql +
  'SELECT '''+TABLE_NAME+''' tbl,'''+COLUMN_NAME+''' col,'+
  ' SUM(CASE WHEN LTRIM(RTRIM('+QUOTENAME(COLUMN_NAME)+'))=@g THEN 1 ELSE 0 END) good_n,'+
  ' SUM(CASE WHEN LTRIM(RTRIM('+QUOTENAME(COLUMN_NAME)+'))=@b THEN 1 ELSE 0 END) bad_n'+
  ' FROM dbo.'+QUOTENAME(TABLE_NAME)+' WITH (NOLOCK) UNION ALL '
FROM INFORMATION_SCHEMA.COLUMNS
WHERE DATA_TYPE IN ('char','varchar','nchar','nvarchar')
  AND (CHARACTER_MAXIMUM_LENGTH >= 36 OR CHARACTER_MAXIMUM_LENGTH = -1);
SET @sql = @sql + 'SELECT ''__end__'','''',0,0';
SET @sql = 'SELECT * FROM ('+@sql+') x WHERE good_n>0 OR bad_n>0 '
         + 'ORDER BY (CASE WHEN good_n>0 AND bad_n=0 THEN 0 ELSE 1 END)';   -- missing rows first
EXEC sp_executesql @sql, N'@g varchar(40),@b varchar(40)', @g=@good, @b=@bad;
```

**Worked example:** a process's dialog steps failed compile with `[Dialog] Could not find the action with ID […]`. The header, refs, and ref-details all existed, but the column-scan showed the known-good dialog had a `t_act_dialog_detail` row (+ its `_h`) the new one lacked. Adding those two rows resolved both errors and the application compiled clean.

## Gotchas

- Some Architect versions have **no "Get Latest"** — the repository is read live/on refresh; reopen the app to pick up raw inserts.
- **Search is application-scoped** — a raw object only appears if its `application_id` matches the app currently open.
- `layer = 10` on these design objects.
- Miss any of the four coordinated rows and the object is invisible or won't compile.
