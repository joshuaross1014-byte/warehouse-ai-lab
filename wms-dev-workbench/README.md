# wms-dev-workbench

A three-layer developer workbench over a Körber/HighJump Advantage-style WMS database on SQL Server:
**front end** (static HTML + JS, no build step) → **back end** (Flask JSON API) → **database**
(SQLAlchemy + pyodbc). Read-only on production by construction. Written as a teaching build, so the
code is meant to be read in a fixed order as much as it is meant to be run.

This is a sanitized reference version: hosts, database names, warehouse codes and site-specific objects
have been replaced with placeholders. Table and column names shown are vendor-standard.

```
browser  ──HTTP /api/*──▶  Flask (app.py + api/*.py)  ──SQLAlchemy──▶  SQL Server (PROD / TEST profiles)
static/index.html             guard.py (read-only gate)                 queries/*.sql (named SQL blocks)
static/app.js                 db.py (engine per profile)                workbench.sqlite (local history)
```

## Run it

```cmd
pip install -r requirements.txt
set WMS_USER=...            # or put them in .env (see .env.example)
set WMS_PASS=...
set WORKBENCH_PROD_SERVER=your-prod-host
set WORKBENCH_TEST_SERVER=your-test-host
run.cmd                     :: foreground, request log in the console; Ctrl+C stops it
start_background.cmd        :: hidden process + opens the browser; logs in server.log
stop.cmd                    :: kills whatever listens on port 8765
```

The server must be running for `http://127.0.0.1:8765` to answer. Nothing starts it automatically.
Needs "ODBC Driver 18 for SQL Server" (override with `WORKBENCH_ODBC_DRIVER`).

## How the layers talk (read the code in this order)

1. **`config.py`** – profiles (PROD red, TEST green), row caps, timeouts. Nothing secret in code; everything
   comes from environment variables or a git-ignored `.env`.
2. **`guard.py`** – every statement is classified `read` or `write`. PROD can never write. TEST writes need
   `WORKBENCH_ALLOW_WRITES=1` *and* the "allow write" checkbox. One statement per request, no `GO`.
   The keyword scan runs on comment-stripped, string-stripped text, so `'update'` in a literal is fine and a
   real `UPDATE` is not.
3. **`db.py`** – one lazy engine per profile (`pool_pre_ping`, `pool_recycle=1800`), ODBC string with the
   password URL-quoted (special characters in passwords are a classic first-day failure), per-call query
   timeout, `fetchmany(cap+1)` so the UI can say "truncated". `load_queries()` parses `queries/*.sql` into a
   dict keyed by `-- name:` headers and refuses duplicates; `named(profile, qname, **params)` runs one with
   bound parameters.
4. **`api/*.py`** – one Flask blueprint per tab. They never build SQL from user input except the single
   whitelisted `SELECT TOP n * FROM <table>` in `schema.sample`. Everything else is a named query with
   `:param` binds, so the key you type is a parameter, never concatenated.
5. **`static/app.js`** – plain DOM. `api()` adds `?profile=`; `resultTable()` renders any `{columns, rows}`
   payload with sort, filter and CSV export; each `viewXxx()` is one tab.

## Tabs

| Tab | Question it answers | Backing queries |
|---|---|---|
| **Ops** | Is the floor healthy right now? Orders/waves/picks by status, wave errors, non-lock host import errors, import queue, RF operators active, open logons, today's transaction mix, locations by zone/status, warehouse control switches, blocking sessions | `queries/ops.sql` |
| **Trace** | Follow one key end to end: **order** (host record → header → lines → waves → picks → HUs → transaction log), **item**, **HU/LP**, **PO** (header → lines → receipts → log), **wave**, **employee** (operator timeline), **location** | `queries/trace.sql` |
| **Schema** | Tables with row counts, columns with PK/identity/defaults, indexes with usage stats, FKs, triggers, "used by" (every module that references the table), find a column across all tables, sample rows | `queries/schema.sql` |
| **Objects** | Search procs/views/functions/triggers by name or body text, definition with line numbers, parameters, uses/used-by dependencies, objects modified recently, plan-cache proc stats | `queries/objects.sql` |
| **SQL** | Guarded ad-hoc statement, local history, saved favourites, the named-query library as a starting point | `api/sql.py` |
| **Diff** | Is PROD running the same proc text as TEST? One object as a unified diff, or a bulk SHA-256 compare of every module matching a pattern (same / differs / one side only) | `api/diff.py` |

Rows are clickable across tabs: a `wave_id` opens the wave trace, an `hu_id` the HU trace, a "used by" row
opens that proc in Objects, and an Objects definition has a "Diff PROD vs TEST" button.

## Why these features, and what to build next

The workbench is organised around the questions a WMS developer actually asks. Each is also a
self-contained exercise if you want to extend it.

**Built**

- *Trace a key through the whole chain.* Most tickets are "where did order X go?". The order trace shows
  the host-interface handshake (`t_al_host_order_master`), allocation (`t_pick_detail`) and what the RF
  guns did (`t_tran_log`) on one screen, newest first.
- *Blast radius before a change.* Schema → "Used by" and Objects → Dependencies answer "what breaks if I
  touch this?" from `sys.sql_expression_dependencies` in both directions.
- *Deploy verification.* Diff → bulk compare is the post-restore / post-compile check: hash every module
  matching a pattern on both servers and list what differs.
- *Index reality check.* Schema → Indexes joins `dm_db_index_usage_stats`, so you can see which indexes are
  actually sought vs only updated before adding another one to `t_tran_log`.
- *Proc hot list.* Objects → Proc stats reads the plan cache without opening Activity Monitor.
- *Config in one place.* Ops → control switches lists every `t_whse_control` row per warehouse.

**Next, roughly by payoff**

1. **Status-code dictionary.** Decode `t_order.status`, `t_pick_detail.status`, `t_wave_master.status` and
   `t_stored_item.status` into labels inside `resultTable()` (a small JSON map).
2. **Timeline view for Trace.** Merge the sections into one chronological event list (host import → wave
   create → release → pick → stage → load → ship) with elapsed-time gaps: the "where did the 40 minutes go?"
   question for late orders.
3. **Panels as monitors.** Each Ops panel is already a named query; add a threshold and a Slack poster (see
   `claude-ops-toolkit/monitors`) and the workbench becomes the monitor runner.
4. **Explain plan.** `SET SHOWPLAN_XML ON` around the SQL-tab statement and render the top operators;
   estimated vs actual rows is the implicit-conversion detector.
5. **Object version history.** Keep a hash + body per module per day and show each proc's history with a
   diff to any prior version, not just PROD vs TEST.
6. **Design-database browser.** On TEST, list RF flow definitions and step versions next to the compiled
   proc, so RF flow → proc → table is one navigation (see `advantage-architect-mcp`).
7. **Stuck-inventory finders.** Panels for recurring pathologies: released picks left behind on shipped
   orders, pallets stranded in receiving staging after an abandoned load, unresolved placeholder license
   plates, stale "full" location flags, staged picks left after ship.
8. **Allocation simulator hook.** Run the allocation rules for an order and show *why* each line got its
   bin (expiry gate, level preference, biggest pile) next to the real `t_pick_detail` rows.
9. **Same statement on both profiles.** Compare elapsed time and reads when TEST has different indexes
   after a restore.
10. **Auth and audit if it ever leaves your laptop.** Windows auth via `Trusted_Connection=yes`, a per-user
    profile allowlist, and an append-only log of every statement.

## Design rules

- Read-only on PROD is a property of the code path, not a checkbox.
- `WITH (NOLOCK)` on every `dbo.*` read.
- Parameters, never string-built SQL, for anything a user types.
- SQL lives in `.sql` files so it can be reviewed, diffed and reused by skills and monitors.
- Nothing from the WMS is persisted locally except your own query-history text.

## Smoke test

```cmd
python -c "import app; c=app.app.test_client(); print(c.get('/api/health').json)"
```

Note that the test client exercises the routes in-process without binding a port. Use `run.cmd` to serve.
