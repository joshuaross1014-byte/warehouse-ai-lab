# 07 - Advantage Architect (REPOSITORY), WebWise and KORE development

Companion to [advantage-architect-mcp](../../../../advantage-architect-mcp/) (the object model) and the compiler-rules section of the wms-engineering `docs/advantage-architect.md`.

## Division of labour

Design objects are built or edited with **raw SQL in the REPOSITORY database** over MCP (clone-with-substitution), staged on TEST first; a human does **Get Latest -> Production Compile -> Activate (Stop and Restart)** in the Architect GUI, because compile/activate is Architect-owned and gates the runtime. Never say a compile or activation is done until the person confirms. Explain every statement, its system effect, and the manual Architect equivalent so the change can be reproduced by hand.

## REPOSITORY schema facts

- `t_app_process_object` = process objects (`subtype` 1 top-level RF entry point, 0 sub-process, 2 callable). `t_app_process_object_detail` **is the flow logic**: `sequence`, `label`, `action_type`, `action_id`, `pass_label` / `fail_label`. `NEXT` = fall through, `PASS`/`FAIL` = return, `PREVIOUS` = jump target; these are not labels. `action_type` maps 1:1 to `t_lkp_object_type`; names resolve from `t_act_calculate`, `t_act_compare`, `t_act_database` (+`_detail` holds the STATEMENT), `t_act_dialog` (+`_detail`, `_ref`, `_ref_detail`), `t_act_execute`, `t_act_list`, `t_act_send`, `t_app_field`, `t_resource` (+`_detail`), `t_app_constant`, `t_app_message`.
- **One current version per object in the main tables.** A new version must REPLACE the old rows in main (back them up to the WMS database first), or the compile fails with "Duplicate Label" x N. History lives in `*_h` tables joined to `t_app_version_control.id` via `version_control_id`. An object checked out in Architect legitimately has a second (working) version until check-in; coordinate before compiling over someone else's check-outs.
- PK of every `*_detail_h` table is `version_control_id` alone, so **every detail row needs its own `t_app_version_control` row** (NEWID-per-row map pattern). Header -> detail tables are `ON DELETE CASCADE`.
- Attribution: create a new `t_app_revision` (new GUID, `application_id`, layer 10, `changed_by` / `developers` = your developer code) and reference it in every `t_app_version_control.revision_id` you write. Never reuse another developer's historical revision.
- Vendor object GUIDs are random, so a short prefix is not unique. Guard and delete by exact id or by revision, never by `LIKE 'A99%'`.
- Objects can exist in main **without** version-control/history rows (vendor work in progress); they are invisible to Architect VC and will not survive a REPOSITORY restore.
- Compile metadata: `t_application_development.last_compiled` is stamped at compile **start**; `t_application_compile` holds in-flight compiles; `t_app_revision` gets a "Compile failed" row only for reported errors. The error file is `ADV.ERR` on the application server, overwritten by each compile. Warnings about unreferenced vendor adapters plus exit code 2 can be normal success.
- Inventory before any compile: apps, counts, recent revisions, check-outs (`locked_by`), and objects with two current versions.

## Compiler rules (learned by failing compiles)

| Rule | Evidence |
|---|---|
| **Description <= 100 chars** on fields, DB actions, compares, calcs | an over-long description crashed the Production Compile silently (no error, no error-file text, no revision row); shortening it fixed the compile with no other change |
| **Keep process objects at <= 37 labels** | proven ceiling on compiled objects; prefer `NEXT` fall-through, blank unreferenced labels, reuse spacer rows (action -1) |
| Even number of single quotes on **every line** of a STATEMENT(); no `--` comments containing apostrophes | "Mismatched Quotes in SQL String" |
| No scalar subquery nested inside a function call (`ISNULL((SELECT ...))`), no double-paren subquery | no compiled precedent; flatten to `SELECT ISNULL(col, 0) FROM ... WHERE ...` and route the 0-rows fail label |
| A DB action returning a datetime into a DATE field stamps a `MM/DD/YY` picture on the prompt | return an MMDDYY string into a string dialog field instead |
| A field cloned from Item ID inherits a UDT subtype that coerces it | set `udt_subtype=0`, `udt_field_id NULL` for free-text session fields |
| Session field length | size for the largest wave you have ever run |

**Pre-compile checklist**: (1) per-line quote parity, (2) no comment apostrophes, (3) no function-wrapped subquery, (4) `SET FMTONLY` bind of every statement against the WMS database, (5) grep the compiled population for any construct not seen there before, (6) description length, (7) label count, (8) one current version per object, (9) nobody has the touched objects checked out.

**When a compile aborts silently**: stop pattern-matching after one round and **bisect by revert**: back up + delete the new work, compile once (clears the environment), re-add leaf objects, compile, then the flow. Then compare the failing object's every column against the compiled population **with your own rows excluded**; a `max == mine` tie is the tell. The compiler only processes an object when a flow references it, so unreferenced leaf objects compile fine and mislead.

## Flow design facts

- The picking F8 list is driven by `t_work_q_assignment` (user + fork zone + pick area), not wave_id.
- `SCR_OPTIONS` (80 chars) is reset per display by the ScrTxt step.
- A flag read once at wave entry is not re-read mid-wave.
- Vendor screens shared by many flows must be cloned, not edited.
- `t_menu` is one tree for all warehouses (menu_level BASE/USER/MGMT, no wh_id); warehouse-specific options need a new menu_level tree. Interleaving dispatcher = `t_intlv_process` (work_type -> process) + `t_intlv_gp_master/_detail`.
- Architect flow logic is **not** stored in the WMS database; `t_whse_control` and `t_control` are what flows read at runtime.

## Deployment pattern (TEST -> PROD)

1. Stage on TEST with dry-run templates (`@commit = 0`, read verification, then `@commit = 1`); lint; human compiles + activates; gun test with a synthetic rig; record the rig cleanup.
2. PROD: same script in a maintenance window (guns off; count open sessions via `t_employee.last_tran_start_datetime`), after the inventory shows no relevant check-outs; backups land in the WMS database; then compile + activate; set switches; smoke; post-checks.
3. Refresh the memory bank's object versions; register the change in the customization inventory and its re-apply kit, because REPOSITORY work does not survive a restore.
4. `SET NOEXEC ON` compile of the deploy script against PROD first.

Test-rig gotchas: an order needs `load_id = order_number` and `t_order_detail.afo_plan_qty = qty` or the recipe is silently empty; `usp_afo_release_wave` only publishes async (use `usp_af_release_wave` directly and wait for `t_allocation_q.status='C'`); the vendor release proc throws a post-commit trancount error, so verify the outcome rather than trusting the exception; use real items and real empty locations because FKs are enforced; clean up temp `t_work_q_assignment` rows.

## WebWise pages (operator web UI)

- Page SQL is **not in SQL Server**. `KoerberOneCore` holds only `PageMetadata`; the report/pick-list SQL lives in `.wdb` config files on the web servers, edited in the **WebWise Page Editor**. Split: write and verify the SQL against production with the operator's parameters, then paste it into the Page Editor and publish. Keep an `ORIGINAL` copy of every page section before changing it.
- A classic defect: a shadowed alias in an `EXISTS ... HAVING` turned a 20-second-timeout page into a full-table GROUP BY; replaced with one correlated predicate it ran in milliseconds. Scan every `*Config .wdb` for the same alias-redeclare pattern.
- Pages that reference missing procs after a restore are simply broken until the SQL objects are re-created.

## KORE / HJ One (`KoerberOneCore`)

The web console is the mobile-app model: `MobileApplication` -> `MobileScreen` -> `PageMetadata`; screen files are varbinary blobs in `dbo.Resource`. The operator client is a client-side JS app calling a backend REST service, so any new action must go through that service layer. Console admin pages are product code; only their backing customer-owned procs can be changed. See [kore-ui-mcp](../../../../kore-ui-mcp/).

## Flow drawings without Visio

Extract from REPOSITORY, curate (drop plumbing, collapse the error tail, detect RF screens by whether a called object reaches a Dialog action), lay out one column per operator interaction, write Mermaid for docs and `.vsdx` for the web Visio (literal cell values only, connectors as true 1-D shapes, elbows as 2-D polylines, text in Character/Paragraph sections, a default StyleSheet 0).
