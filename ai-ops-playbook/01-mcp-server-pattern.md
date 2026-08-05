# 01 — The MCP Server Pattern

Two archetypes cover every database an AI assistant needs to reach: one that can write (behind a
human gate) and one that structurally cannot. Every server in a real estate is a copy of one of
them with a different connection helper.

Full source below. Names, hosts, and schemas are generic.

## Architecture in one page

MCP (Model Context Protocol) is how an AI client calls tools on an external process. Each server
here is a single Python file that:

1. connects to one target database through a shared connection helper,
2. exposes exactly five tools,
3. runs as a **local child process over stdio** — no listening port, no web service, no new attack
   surface. The only network traffic is the same driver connection any admin tool would make.

Registration is one entry per server in the client's config:

```json
{
  "mcpServers": {
    "warehouse":     { "command": "C:\\path\\to\\python.exe", "args": ["C:\\path\\to\\wms_mcp_server.py"] },
    "erp_readonly":  { "command": "C:\\path\\to\\python.exe", "args": ["C:\\path\\to\\erp_mcp_server.py"] }
  }
}
```

The five-tool surface is identical across every server, so the model's muscle memory transfers
between systems:

| Tool | Purpose |
|---|---|
| `run_sql(sql, max_rows)` | Execute a statement or batch — the only tool that differs by archetype |
| `list_tables(schema, name_like)` | Enumerate tables from the system catalog |
| `describe_table(table, schema)` | Column definitions (type, nullability, length, position) |
| `get_object_definition(name)` | Source of a stored procedure / view / function / trigger |
| `test_connection()` | Prove connectivity **and identity** — server, database, authenticated login, time |

---

## Archetype A — read-write (SQL Server)

```python
# ------------------------------------------------------------
# wms_mcp_server.py
# Purpose : Local stdio MCP server giving an AI assistant direct, real-time
#           access to the warehouse management database.
# Access  : READ-WRITE. run_sql() commits DML/DDL. The service login has
#           broad rights, so this channel CAN mutate production.
#           Confirmation before any write is the governing rule.
# ------------------------------------------------------------

import os
import sys
import decimal
import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from db_connect import get_engine, SERVER, DATABASE

# Fail fast and loudly if creds are missing, rather than letting the connection
# helper fall back to input()/getpass() -- that would hang a stdio MCP process.
if not (os.getenv("DB_USER") and os.getenv("DB_PASS")):
    sys.stderr.write(
        "FATAL: DB_USER / DB_PASS environment variables are not set. "
        "Set them at the User level before launching the MCP server.\n"
    )
    sys.exit(1)

mcp = FastMCP("warehouse")

DEFAULT_MAX_ROWS = 1000


def _jsonable(value: Any) -> Any:
    """Coerce DB values into JSON-serializable Python types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        # preserve precision as string; ints stay ints
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


@mcp.tool()
def run_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> dict:
    """Execute SQL against the warehouse database and return results.

    READ-WRITE. The statement runs inside a transaction that COMMITS on success
    and ROLLS BACK on error. SELECTs return rows; DML/DDL returns affected
    row counts. Handles batches with multiple result sets.

    Conventions for this database:
      - Add WITH (NOLOCK) to every dbo.* table read to avoid blocking production.
      - This channel CAN mutate production data. Only run INSERT/UPDATE/DELETE/
        MERGE/TRUNCATE or any CREATE/ALTER/DROP/EXEC after explicit user
        confirmation.

    Args:
        sql: The T-SQL statement or batch to execute.
        max_rows: Cap on rows returned per result set (default 1000). Extra rows
                  are dropped and the result set is flagged truncated=True.

    Returns:
        dict with server/database, and a list of result_sets. Each result set has
        columns, rows (list of dicts), row_count, truncated, and for non-SELECT
        statements an affected_rows count.
    """
    engine = get_engine()
    out: dict = {"server": SERVER, "database": DATABASE, "result_sets": []}

    with engine.begin() as conn:                      # auto-commit boundary
        raw = conn.connection.dbapi_connection        # underlying pyodbc connection
        cur = raw.cursor()
        try:
            cur.execute(sql)
            while True:
                if cur.description is not None:
                    cols = [d[0] for d in cur.description]
                    fetched = cur.fetchall()
                    total = len(fetched)
                    limited = fetched[:max_rows]
                    rows = [
                        {c: _jsonable(v) for c, v in zip(cols, row)}
                        for row in limited
                    ]
                    out["result_sets"].append({
                        "type": "rows",
                        "columns": cols,
                        "row_count": total,
                        "rows": rows,
                        "truncated": total > max_rows,
                    })
                else:
                    out["result_sets"].append({
                        "type": "statement",
                        "affected_rows": cur.rowcount,
                    })
                if not cur.nextset():
                    break
        finally:
            cur.close()

    if not out["result_sets"]:
        out["result_sets"].append({"type": "statement", "affected_rows": 0})
    return out


@mcp.tool()
def list_tables(schema: str = "dbo", name_like: str = "") -> dict:
    """List tables in the database, optionally filtered by a name pattern."""
    sql = """
        SELECT s.name AS [schema], t.name AS [table], t.create_date, t.modify_date
        FROM sys.tables t WITH (NOLOCK)
        JOIN sys.schemas s WITH (NOLOCK) ON s.schema_id = t.schema_id
        WHERE s.name = ?
          AND (? = '' OR t.name LIKE '%' + ? + '%')
        ORDER BY t.name;
    """
    engine = get_engine()
    with engine.connect() as conn:
        cur = conn.connection.dbapi_connection.cursor()
        try:
            cur.execute(sql, (schema, name_like, name_like))
            cols = [d[0] for d in cur.description]
            rows = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        finally:
            cur.close()
    return {"schema": schema, "count": len(rows), "tables": rows}


@mcp.tool()
def describe_table(table: str, schema: str = "dbo") -> dict:
    """Return column definitions (name, type, nullability, length) for a table."""
    sql = """
        SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
               c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE, c.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS c WITH (NOLOCK)
        WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
        ORDER BY c.ORDINAL_POSITION;
    """
    engine = get_engine()
    with engine.connect() as conn:
        cur = conn.connection.dbapi_connection.cursor()
        try:
            cur.execute(sql, (schema, table))
            cols = [d[0] for d in cur.description]
            rows = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        finally:
            cur.close()
    return {"schema": schema, "table": table, "columns": rows}


@mcp.tool()
def get_object_definition(name: str) -> dict:
    """Return the T-SQL definition of a stored procedure, view, function, or
    trigger from sys.sql_modules. Accepts bare or schema-qualified names."""
    sql = """
        SELECT OBJECT_SCHEMA_NAME(m.object_id) AS [schema],
               OBJECT_NAME(m.object_id)        AS [name],
               o.type_desc,
               m.definition
        FROM sys.sql_modules m WITH (NOLOCK)
        JOIN sys.objects o WITH (NOLOCK) ON o.object_id = m.object_id
        WHERE m.object_id = OBJECT_ID(?);
    """
    engine = get_engine()
    with engine.connect() as conn:
        cur = conn.connection.dbapi_connection.cursor()
        try:
            cur.execute(sql, (name,))
            row = cur.fetchone()
            if row is None:
                return {"found": False, "name": name}
            cols = [d[0] for d in cur.description]
            rec = {c: _jsonable(v) for c, v in zip(cols, row)}
        finally:
            cur.close()
    rec["found"] = True
    return rec


@mcp.tool()
def test_connection() -> dict:
    """Confirm connectivity. Returns the server name, current database, the
    authenticated login, and server time."""
    engine = get_engine()
    with engine.connect() as conn:
        cur = conn.connection.dbapi_connection.cursor()
        try:
            cur.execute("SELECT @@SERVERNAME, DB_NAME(), SUSER_SNAME(), SYSDATETIME();")
            srv, db, login, now = cur.fetchone()
        finally:
            cur.close()
    return {
        "server_name": _jsonable(srv),
        "database_name": _jsonable(db),
        "login_name": _jsonable(login),
        "server_time": _jsonable(now),
    }


if __name__ == "__main__":
    mcp.run()   # stdio transport
```

### What to notice

**The header is a contract.** Access level and the governing rule are declared before any code
runs. Anyone opening this file knows within five seconds what it can do to production.

**Fail fast on missing credentials.** No credentials live in the code — they come from environment
variables. If absent, the server exits with a FATAL message. The reason is specific: connection
helpers often fall back to interactive `getpass()`, which would silently hang a stdio process
forever, presenting as "the tools just don't work" with no error anywhere.

**`run_sql` is transactional all-or-nothing.** `with engine.begin()` commits only if the whole
batch succeeds and rolls back on any error. A half-applied multi-statement change cannot be left
behind.

**Multi-result-set batches work.** The `cur.nextset()` loop walks every result set a batch
produces, so a diagnostic script returning counts + samples + summary comes back complete. This is
why the code drops to the raw DBAPI cursor instead of staying in SQLAlchemy's result API.

**Truncation is honest.** Results are capped and the response says `truncated: true` when the cap
bites. The model can never mistake a capped result for a complete one — a subtle but real source
of wrong conclusions.

**The docstring is the policy delivery mechanism.** The model re-reads a tool's docstring on every
call. That is why the locking convention and the confirm-before-write rule live *inside*
`run_sql`'s docstring rather than in a README. A rule in a README is read once; a rule in a
docstring is delivered at the moment of use, every time.

**Metadata tools are injection-safe** — parameterized queries throughout, never string
concatenation.

**`_jsonable` protects precision.** Quantities and money arrive as `Decimal`. Casting to `float`
introduces binary floating-point error into inventory numbers; casting everything to `str` makes
whole numbers awkward to compare. So integral decimals become `int`, fractional ones become
**strings**. Precision is never silently lost — a data-integrity control disguised as a
serialization detail.

---

## Archetype B — fail-closed read-only (SAP HANA)

Same shape, one critical addition: a statement gate in front of execution.

```python
# ------------------------------------------------------------
# erp_mcp_server.py
# Access  : READ-ONLY. The service login holds only SELECT (+ CATALOG READ) on
#           the ERP schemas, so it cannot mutate data. As a second, independent
#           guard, run_sql() rejects anything that is not SELECT/WITH/EXPLAIN.
# ------------------------------------------------------------

from mcp.server.fastmcp import FastMCP
from erp_connect import get_connection, HOST, PORT, SCHEMA

mcp = FastMCP("erp_readonly")

DEFAULT_MAX_ROWS = 1000

# Statements this read-only channel is allowed to run (first keyword).
_ALLOWED_FIRST = {"SELECT", "WITH", "EXPLAIN"}


def _first_keyword(sql: str) -> str:
    """Return the leading SQL keyword, ignoring wrapping parens/whitespace."""
    s = sql.lstrip()
    while s.startswith("("):
        s = s[1:].lstrip()
    return (s.split(None, 1)[0].upper() if s else "")


@mcp.tool()
def run_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> dict:
    """Execute a READ-ONLY query against the ERP database.

    READ-ONLY. Only SELECT / WITH / EXPLAIN statements are accepted; anything
    else is rejected without execution. (The service login also cannot write at
    the database level -- this is a second guard.)

    Conventions for this database:
      - HANA is in-memory + MVCC: reads never block writers, so no NOLOCK hint
        is needed or available.
      - Qualify schemas explicitly when crossing them.
      - Object names are case-sensitive and usually upper-case; quote them with
        double quotes when needed.
    """
    first = _first_keyword(sql)
    if first not in _ALLOWED_FIRST:
        return {
            "error": "read-only channel: only SELECT / WITH / EXPLAIN are allowed.",
            "rejected_statement": first or "(empty)",
        }

    out: dict = {"host": HOST, "port": PORT, "schema": SCHEMA, "result_sets": []}
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        if cur.description is not None:
            cols = [d[0] for d in cur.description]
            fetched = cur.fetchall()
            total = len(fetched)
            rows = [
                {c: _jsonable(v) for c, v in zip(cols, row)}
                for row in fetched[:max_rows]
            ]
            out["result_sets"].append({
                "type": "rows", "columns": cols, "row_count": total,
                "rows": rows, "truncated": total > max_rows,
            })
        else:
            out["result_sets"].append({"type": "statement", "affected_rows": cur.rowcount})
    finally:
        cur.close()
        conn.close()
    return out


@mcp.tool()
def get_object_definition(name: str, schema: str = SCHEMA) -> dict:
    """Return the SQL definition of a view, procedure, or function.

    Searches VIEWS, then PROCEDURES, then FUNCTIONS -- HANA splits them across
    separate catalog views. Names are matched case-insensitively.
    """
    lookups = [
        ("VIEW", "SYS.VIEWS", "VIEW_NAME"),
        ("PROCEDURE", "SYS.PROCEDURES", "PROCEDURE_NAME"),
        ("FUNCTION", "SYS.FUNCTIONS", "FUNCTION_NAME"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    try:
        for obj_type, view, col in lookups:
            cur.execute(
                f"SELECT SCHEMA_NAME, {col} AS OBJECT_NAME, DEFINITION "
                f"FROM {view} WHERE SCHEMA_NAME = ? AND UPPER({col}) = UPPER(?)",
                (schema, name),
            )
            row = cur.fetchone()
            if row is not None:
                cols = [d[0] for d in cur.description]
                rec = {c: _jsonable(v) for c, v in zip(cols, row)}
                rec["object_type"] = obj_type
                rec["found"] = True
                return rec
    finally:
        cur.close()
        conn.close()
    return {"found": False, "schema": schema, "name": name}
```

*(`list_tables`, `describe_table`, and `test_connection` mirror archetype A against the HANA
catalog views: `SYS.TABLES`, `SYS.TABLE_COLUMNS`, and `SYS.M_DATABASE` + `CURRENT_USER`.)*

### What to notice

**The gate is an allowlist, not a blocklist — and that is the whole point.** `DELETE`,
`/*comment*/DELETE`, `--\nDELETE`, and `(DELETE ...)` all fail identically: none of them match
SELECT/WITH/EXPLAIN, so all are rejected before any network I/O. A blocklist would have to
anticipate every evasion; an allowlist does not. The paren-stripping loop exists so a wrapped
statement cannot smuggle a different first keyword past the check.

**Two independent layers, neither trusting the other:**

| Layer | Mechanism | What it stops |
|---|---|---|
| Database account | Service login holds only SELECT + CATALOG READ | Any write, even if the code layer were bypassed entirely |
| Code gate | First-keyword allowlist | Any write attempt before it leaves the process |

The result is that writes to this system are not *prevented by policy* — they are impossible as a
property of the system.

**Engine differences are encoded, not remembered.** The docstring conventions differ from
archetype A because the engines differ: MVCC means no lock hints exist, object names are
case-sensitive, cross-schema reads need qualification. Writing this into the docstring means the
model gets it right without being reminded.

---

## Why the write-capable channel has no keyword gate

This is the question every reviewer asks, so it is worth answering directly.

The write channel exists **so that fixes can ship** — stored procedure changes, design objects,
hotfixes. Write capability is the point. Adding a keyword filter there would only push real work
onto worse paths (someone pasting SQL into a GUI with no audit trail).

The correct control for *intentional* capability is a human gate plus verification plus rollback.
The correct control for a channel that must *never* write is code plus account permissions.
Different risk, different mechanism. Applying the read-only pattern everywhere would look more
consistent and be less safe, because it would drive the risky work somewhere unobserved.

---

## Adding a new system

Because every server is the same two files with a different connection helper, adding a target is
a copy-plus-config exercise:

1. Copy the archetype that matches the access level the system should have.
2. Point it at a connection helper for the new engine.
3. Provision a **least-privilege account** — for read-only targets, use an admin account exactly
   once to create and grant the query-only user, then retire it.
4. Register the server in the client config.
5. Run `test_connection()` and confirm the returned login is the one you expect.

Step 5 is not ceremony. `test_connection` returning the authenticated identity is how you prove a
session is operating as the account you intended, before any work happens.

---

*Next: [02 — Safety model](02-safety-model.md)*
