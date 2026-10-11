---
name: wms-knowledge
description: Körber/HighJump Advantage-style WMS (SQL Server) domain knowledge for analysis, troubleshooting and development. Decoded facts that are NOT derivable from the schema - status codes, order types, dead columns, the ERP (SAP Business One) integration contract, allocation and autowave rules, receiving/RF pathologies, production cleanup recipes, design-database compiler rules, and how to inventory site customizations and switches. Use whenever a question touches WMS behaviour, a WMS table or proc, an RF gun symptom, a wave/pick/receipt problem, ERP-to-WMS order flow, or before designing or deploying any WMS change. Read the matching reference file before querying or answering.
---

# WMS domain knowledge (Körber/HighJump Advantage on SQL Server)

Everything here was learned by executing queries against production and test instances and by deploying real changes. **Facts age: re-verify live anything you are about to act on.** Operating rules (confirm before production writes, NOLOCK, cache-first lookup) live in CLAUDE.md, not here. Site-specific values (hosts, warehouse codes, custom object names) are placeholders; fill them in for your instance.

## How to use this skill

1. Find the topic below, read **only that reference file** (`references/NN-*.md`). Do not load all eight.
2. Cross-check against the memory bank (`recall`, `schema`) for anything newer than the file.
3. If you learn something durable that contradicts or extends a file, say so in your answer and record it; the files are refreshed from the memory bank periodically.

| Question is about | Read |
|---|---|
| Environments, databases, warehouses, wave-id prefixes, order types, status codes, tran_types, key tables, staging locations | `references/01-environment-and-codes.md` |
| Writing SQL: dead columns, type mismatches, the 1900-01-01 time base, control characters, the MCP transaction wrapper, catalog visibility traps, collation | `references/02-schema-gotchas.md` |
| ERP (SAP Business One) to WMS and back: staging tables, the export-flag handshake, order lock, per-interface services, benign import errors, empty POs, delivery failures, transfer close not propagated | `references/03-erp-wms-integration.md` |
| Allocation rules (FEFO/LEFO/custom profiles), autowave and autorelease design, wave lifecycle, pick splits, RF list order | `references/04-allocation-waves-automation.md` |
| Receiving, putaway, RF sessions and devices, catch-weight barcodes, staging-location roles, pallets in the wrong place, Full flag, BOL gates, expiry dating, held stock, foreign-character crashes | `references/05-receiving-inventory-rf.md` |
| A recipe to fix production data: stuck wave teardown, orphan picks, staged orphans, outbound pallets in receiving staging, token LPs, LPN on item-managed stock, stranded RF batch | `references/06-cleanup-recipes.md` |
| Design-database (Architect / REPOSITORY) raw-SQL development, compiler rules, versioning, attribution, silent-compile bisect, web-page SQL, test rigs | `references/07-architect-webwise-development.md` |
| What customizations, switches, Agent jobs and design-database changes exist, what survives a restore, how to inventory them | `references/08-customization-inventory.md` |

## Ten facts that prevent the most wrong answers

1. `t_order.status`: N new, B waved (also set by Cancel), S shipped (set at ship-confirm regardless of fill rate), D picked/staged-done. `t_wave_master.status`: N new, H hold, A allocating, R released. `t_stored_item.status`: A available, H hold, U unavailable (physical counts create U stock and nothing releases it).
2. Order types live in `t_lookup` (source t_order): vendor defaults for sales, transfer, cross-dock and return-to-vendor, plus any custom types your site registered (outbound vs inbound variants are different ids).
3. `t_al_host_order_master.import_status='E'` is mostly benign: "Picking has started" / "Order is already added to wave" = the WMS correctly refusing the ERP's periodic re-export of an open order. Filter those two messages out before calling anything an import failure.
4. Allocation happens at wave **release**, at the grain location + lot, never LP. RF flows only show picks that have a `t_allocation` row; a RELEASED pick with no allocation is invisible on the gun.
5. `t_device` is dead; live gun state is `t_employee` (device, wh_id, last_tran_*) and `t_employee_logon`. A device asset tag says nothing about its warehouse. Retired voice objects (`t_vo_*`, `usp_vo_*`) mislead.
6. `t_tran_log.start_tran_date` is midnight; time-of-day lives in `start_tran_time` on a 1900-01-01 base. `elapsed_time` is correct across midnight. Join `t_tran_log.employee_id` (nvarchar) to `t_employee.id`, not `employee_id` (int).
7. Know which staging location is item-managed (`t_location.item_hu_indicator='I'`): an LPN on item-managed stock is a receiving defect that loops the gun. The default putaway target (`DEF_STG_LOC_PUTAWAY`) is where abandoned fork loads end up.
8. An MCP `run_sql` session wraps each call in a transaction. Vendor procs that commit internally (`usp_allocate`, `usp_af_release_wave`) throw error 266, and any error anywhere in a batch rolls back an otherwise successful ALTER. Run DDL alone, verify in a separate call; use an autocommit connection for those procs.
9. A database restore carries only what is inside that database. SQL Agent jobs (msdb), design-database work (RF flows, statements) and web-page SQL stored in config files do **not** survive a restore or platform upgrade. Keep idempotent re-apply kits (reference 08).
10. An automated "orphan pick" janitor that keys only on order status will close live partial-shipment work, because ship-confirm sets the order to S regardless of fill rate. Any such job needs a completeness gate.
