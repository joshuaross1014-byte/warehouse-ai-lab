# kore-ui-mcp

Inspect and edit a Körber (HighJump One) WMS's **web UI** with an AI assistant — the web analogue of [`advantage-architect-mcp`](../advantage-architect-mcp/) (which does the RF-gun side).

The modern web platform (HJ One / Körber One) is **DB-defined**: its mobile/operator apps, screens, and workflows live in a SQL Server database. This project exposes that database over MCP so pages can be read and edited as SQL. It also maps the **legacy WebWise** layer — older config-driven web pages whose definitions live in per-page Microsoft Access files on the app server, behind a publish pipeline — and the safe **read-only-inspect + apply-in-editor** workflow used for those.

> Sanitized reference. Connection targets and credentials come from environment variables. `HJOneCore` is the vendor product's database name.

## Two web layers (important)

| Layer | Where its config lives | How you change it |
|---|---|---|
| **HJ One / Körber One** (SCA inMotion operator client, admin console) | a SQL Server database (`HJOneCore`); the mobile-app model `MobileApplication → MobileScreen → PageMetadata`, with screen HTML/JS/CSS stored as blobs in a `Resource` table | **directly via this MCP** (it's a SQL database) |
| **WebWise** (legacy Accellos web pages, e.g. device/session admin) | **per-page Microsoft Access `.wdb` files** on the web app server, exposed via 32-bit ODBC DSNs, behind a **publish pipeline** | **read-only inspect** (PowerShell) → **author the SQL** → apply in the **WebWise Page Editor** (which publishes). A raw external write would skip publish and risks corrupting a single-file DB the live app holds open. |

The rule of thumb: HJ One / operator client / admin console → this MCP; the older WebWise pages → the Page-Editor apply flow. See [`NOTES.md`](NOTES.md).

## What's here

| File | Purpose |
|---|---|
| [`kore_mcp_server.py`](kore_mcp_server.py) | Local MCP server over the HJ One web-UI database (`run_sql` / `list_tables` / `describe_table` / `test_connection`). |
| [`NOTES.md`](NOTES.md) | The HJ One vs WebWise architecture and the read-only-inspect + apply-in-editor workflow. |
| [`webwise_recon.ps1`](webwise_recon.ps1) | One-time-per-server, read-only: enumerates the `*Config` DSNs → `.wdb` files, driver bitness, and confirms a read opens. |
| [`webwise_inspect.ps1`](webwise_inspect.ps1) | Read-only: dumps one WebWise page (master + fields + picklists + SQL + links + workflow) so a change can be authored precisely. |

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install "mcp[cli]" pyodbc
cp .env.example .env      # DB_SERVER / WEBUI_DB / DB_USER / DB_PASS
```

Requires the **ODBC Driver 18 for SQL Server**. The WebWise PowerShell scripts run on the web app server in **32-bit PowerShell** (the Access driver is 32-bit) and are read-only.
