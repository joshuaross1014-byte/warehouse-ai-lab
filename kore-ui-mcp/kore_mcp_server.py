# ------------------------------------------------------------
# kore_mcp_server.py
# Local stdio MCP server exposing a Körber (HJ One / Körber One) WMS
# web-UI definition database to an AI assistant, so operator/admin
# web pages can be inspected and edited as SQL.
#
# The web UI is DB-defined: MobileApplication -> MobileScreen ->
# PageMetadata, with screen HTML/JS/CSS stored as blobs in a Resource
# table. (The older WebWise pages live in Access .wdb files instead --
# see NOTES.md; those are edited via the Page Editor, not this server.)
#
# Connection target + credentials come from environment variables
# (or a local .env). READ-WRITE; run_sql() commits on success, rolls
# back on error. Treat any write like a UI change -- validate first.
# ------------------------------------------------------------

import os
import sys
import decimal
import datetime
from typing import Any

import pyodbc
from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                override=False)
except ImportError:
    pass

SERVER   = os.getenv("DB_SERVER", "localhost")
WEBUI_DB = os.getenv("WEBUI_DB", "HJOneCore")   # HJ One web-UI definition DB
DRIVER   = "ODBC Driver 18 for SQL Server"

if not (os.getenv("DB_USER") and os.getenv("DB_PASS")):
    sys.stderr.write("FATAL: set DB_USER / DB_PASS (and DB_SERVER) before launching.\n")
    sys.exit(1)

mcp = FastMCP("kore_ui")
DEFAULT_MAX_ROWS = 1000


def _connect():
    cs = (
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={WEBUI_DB};"
        f"UID={os.environ['DB_USER']};PWD={os.environ['DB_PASS']};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(cs, autocommit=False)


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return str(v)


@mcp.tool()
def run_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> dict:
    """Execute a T-SQL batch against the web-UI database. READ-WRITE, transactional
    (commit on success, rollback on error). Add WITH (NOLOCK) to reads by habit."""
    cx = _connect(); cur = cx.cursor(); out = {"server": SERVER, "database": WEBUI_DB, "result_sets": []}
    try:
        cur.execute(sql)
        while True:
            if cur.description is not None:
                cols = [d[0] for d in cur.description]
                fetched = cur.fetchall()
                rows = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in fetched[:max_rows]]
                out["result_sets"].append({"type": "rows", "columns": cols,
                                           "row_count": len(fetched), "rows": rows,
                                           "truncated": len(fetched) > max_rows})
            else:
                out["result_sets"].append({"type": "statement", "affected_rows": cur.rowcount})
            if not cur.nextset():
                break
        cx.commit()
    except Exception:
        cx.rollback(); raise
    finally:
        cur.close(); cx.close()
    if not out["result_sets"]:
        out["result_sets"].append({"type": "statement", "affected_rows": 0})
    return out


@mcp.tool()
def list_tables(schema: str = "dbo", name_like: str = "") -> dict:
    """List tables in the web-UI DB, optionally filtered by a name substring."""
    sql = ("SELECT s.name AS [schema], t.name AS [table] FROM sys.tables t WITH (NOLOCK) "
           "JOIN sys.schemas s WITH (NOLOCK) ON s.schema_id=t.schema_id "
           "WHERE s.name=? AND (?='' OR t.name LIKE '%'+?+'%') ORDER BY t.name")
    cx = _connect(); cur = cx.cursor()
    try:
        cur.execute(sql, (schema, name_like, name_like))
        cols = [d[0] for d in cur.description]
        rows = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    finally:
        cur.close(); cx.close()
    return {"schema": schema, "count": len(rows), "tables": rows}


@mcp.tool()
def describe_table(table: str, schema: str = "dbo") -> dict:
    """Return column definitions for a table."""
    sql = ("SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, ORDINAL_POSITION "
           "FROM INFORMATION_SCHEMA.COLUMNS WITH (NOLOCK) WHERE TABLE_SCHEMA=? AND TABLE_NAME=? "
           "ORDER BY ORDINAL_POSITION")
    cx = _connect(); cur = cx.cursor()
    try:
        cur.execute(sql, (schema, table))
        cols = [d[0] for d in cur.description]
        rows = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    finally:
        cur.close(); cx.close()
    return {"schema": schema, "table": table, "columns": rows}


@mcp.tool()
def test_connection() -> dict:
    """Confirm connectivity; returns server, database, login, and time."""
    cx = _connect(); cur = cx.cursor()
    try:
        cur.execute("SELECT @@SERVERNAME, DB_NAME(), SUSER_SNAME(), SYSDATETIME()")
        srv, db, login, now = cur.fetchone()
    finally:
        cur.close(); cx.close()
    return {"server_name": _jsonable(srv), "database_name": _jsonable(db),
            "login_name": _jsonable(login), "server_time": _jsonable(now),
            "configured_server": SERVER}


if __name__ == "__main__":
    mcp.run()
