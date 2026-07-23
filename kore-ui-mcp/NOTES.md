# Körber web UI — architecture & change workflows

Two distinct web layers ship with this WMS. Knowing which one a page belongs to determines how you change it.

## 1. HJ One / Körber One  (DB-defined → edit via MCP)

The modern platform (operator client "SCA inMotion", plus the admin console) stores its UI in a SQL Server database (`HJOneCore`):

- **`MobileApplication`** → **`MobileScreen`** → **`PageMetadata`** — the app/screen/page model.
- The actual screen files (HTML / JS / CSS) are stored as **`varbinary` blobs in a `Resource`** table, keyed by filename + application id.
- Workflows in `WorkflowDefinition` / `CompositeWorkflow`; print templates in `PrintLabelTemplate`.

Because it's a SQL database, `kore_mcp_server.py` can read and edit it directly. Treat any write like a UI change — validate on a test tenant first.

## 2. WebWise  (Access files → read-only inspect + apply-in-editor)

The **legacy Accellos "WebWise"** pages (older search/admin pages) are *not* SQL Server:

- Each web "config" is a **Microsoft Access `.wdb` file** on the web app server's disk, exposed through **32-bit Access-driver ODBC DSNs** (one per config).
- Each `.wdb` is a ~60-table relational model of the pages: `t_web_page_master` (pages), `t_web_column_attribute` (per-field attributes + SQL), `t_web_page_edit_picklist` (+`_sql`) (dropdowns), `t_web_page_edit_validation` (validation SQL), `t_web_menu`, `t_web_link*`, `t_web_page_button*`, `t_web_page_nav*`, `t_resource` (labels).
- There is a **publish pipeline** (`t_publish_status` / `publish_url` / `published_date_utc`): the Page Editor's save both writes the config rows **and publishes**. A raw external write skips publish (the change won't propagate) and risks corrupting a single-file Access DB the live app holds open.

### Why there's no live read/write MCP for WebWise

- No SQL endpoint — the config is Access files on the app server (not a DB server).
- The files aren't reachable off-box, the driver is 32-bit, and a runtime would have to be installed on a production web server.
- The publish pipeline means direct writes wouldn't take effect the same way.

So the safe pattern is **read-only inspect + apply-in-editor**:

1. Identify the page (config/DSN + page id) from the Page Editor.
2. Run `webwise_recon.ps1` once per server (confirms driver/DSN→`.wdb` mapping), then `webwise_inspect.ps1` for the page (dumps its fields, picklists, SQL, links, workflow) — both **read-only**, in 32-bit PowerShell on the web app server.
3. Author the exact change as SQL / field settings.
4. Paste it into the **WebWise Page Editor** and save — which runs the publish.

### Worked example

A device-admin search page's drop-down listed all locations with the wanted default buried at the bottom, and its location query was hardcoded to one warehouse. The fix was a two-line edit to the field's PickList SQL (a `CASE`-based `ORDER BY` to pin the preferred location first, plus using the warehouse token instead of a hardcoded value) — authored from the read-only dump, applied in the editor.
