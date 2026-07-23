# advantage-architect-mcp

Develop a Körber / HighJump **Advantage WMS**'s RF-gun screens, menus, fields, and process flows **directly in raw SQL** — over the Model Context Protocol — instead of clicking through the Architect GUI.

Advantage stores its RF application design in a SQL Server **design database** (the runtime reads its compiled output). This project exposes that design database to an AI assistant over MCP and documents the reverse-engineered object model, so new RF flows can be authored, cloned, and fixed as SQL. The only step that still happens in the Architect GUI is **Compile + Activate** (which publishes the design to the runtime and can't be done from SQL).

> Sanitized reference. Connection targets and credentials come from environment variables — no hostnames, instances, logins, or passwords in source. Table/object names shown are the vendor's standard Advantage schema.

## Why this is useful

RF-flow changes on a packaged WMS normally mean GUI clicking or a vendor engagement. Modeling the design database directly makes changes **scriptable, reviewable, diff-able, and fast** — and lets an AI assistant read the existing objects and propose exact edits. The methodology below was reverse-engineered against a live multi-warehouse deployment.

## What's here

| File | Purpose |
|---|---|
| [`architect_mcp_server.py`](architect_mcp_server.py) | Local MCP server exposing the design DB (`run_sql` / `list_tables` / `describe_table` / `get_object_definition` / `test_connection`). Reads/writes are env-configured; `run_sql` is transactional (commit on success, rollback on error). |
| [`METHODOLOGY.md`](METHODOLOGY.md) | The reverse-engineered object model: menu → process → action tables, the mandatory 4-table version-control pattern, the action-type map, dialog/screen anatomy, and a column-scan technique for diagnosing compile errors. |
| `.env.example` | Copy to `.env` and fill in your own connection values. |

## How it fits together

```
RF menu (runtime)  ->  process object (+ ordered steps)  ->  action tables
                                                              ├─ DB action  (calls a stored proc)
                                                              ├─ dialog     (a screen prompt/message)
                                                              ├─ compare / calculate (flow logic)
                                                              └─ terminator (PASS / FAIL)
```

Each design object is written across **four coordinated tables** (main row + history row + a version-control row + a revision it points to) or the compiler won't see it. New objects are built by **cloning a known-good object and substituting IDs/values** — see `METHODOLOGY.md`.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install "mcp[cli]" pyodbc
cp .env.example .env      # fill in DB_SERVER / DESIGN_DB / DB_USER / DB_PASS
```

Requires the **ODBC Driver 18 for SQL Server**. Register the server with your MCP client (e.g. Claude Code / Claude Desktop) pointing at `architect_mcp_server.py`.

## Safety

- Reads default to `WITH (NOLOCK)` by convention; every write runs in a transaction that rolls back on error.
- Production writes should stay behind an explicit human confirmation — the design DB backs the live RF application.
- Compile + Activate is deliberately left to a human in the Architect GUI.
