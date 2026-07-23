# ------------------------------------------------------------
# architect_mcp_server.py
# Local stdio MCP server exposing a Körber/HighJump Advantage WMS
# *design* database (the Architect repository) to an AI assistant,
# so RF-flow objects can be inspected and authored directly in SQL.
#
# Connection target + credentials come from environment variables
# (or a local .env) -- no hostnames, logins, or passwords in source.
# Defaults: DESIGN_DB=REPOSITORY (design), RUNTIME_DB=AAD (runtime).
# The design DB is the default catalog; the runtime DB and any other
# database on the instance are reachable via 3-part names.
#
# READ-WRITE. run_sql() runs inside a transaction that COMMITS on
# success and ROLLS BACK on error. Production writes should stay behind
# an explicit human confirmation; Compile + Activate stays in the GUI.
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

SERVER    = os.getenv("DB_SERVER", "localhost")
DESIGN_DB = os.getenv("DESIGN_DB", "REPOSITORY")   # Architect design database
DRIVER    = "ODBC Driver 18 for SQL Server"

if not (os.getenv("DB_USER") and os.getenv("DB_PASS")):
    sys.stderr.write("FATAL: set DB_USER / DB_PASS (and DB_SERVER) before launching.\n")
    sys.exit(1)

mcp = FastMCP("advantage_architect")
DEFAULT_MAX_ROWS = 1000


def _connect():
    cs = (
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DESIGN_DB};"
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
    """Execute a T-SQL batch against the design database.

    READ-WRITE. The batch runs in a transaction that COMMITS on success and
    ROLLS BACK on error. SELECTs return rows; DML/DDL returns affected counts.
    Add WITH (NOLOCK) to reads by habit. Other databases on the instance are
    reachable via 3-part names (e.g. RUNTIME_DB.dbo.<table>).
    """
    cx = _connect(); cur = cx.cursor(); out = {"server": SERVER, "database": DESIGN_DB, "result_sets": []}
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
    """List tables in the design DB, optionally filtered by a name substring."""
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
    """Return column definitions (name, type, length, nullability) for a table."""
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
def get_object_definition(name: str) -> dict:
    """Return the T-SQL definition of a proc/view/function/trigger."""
    sql = ("SELECT OBJECT_SCHEMA_NAME(object_id) [schema], OBJECT_NAME(object_id) name, definition "
           "FROM sys.sql_modules WITH (NOLOCK) WHERE object_id=OBJECT_ID(?)")
    cx = _connect(); cur = cx.cursor()
    try:
        cur.execute(sql, (name,))
        row = cur.fetchone()
        if row is None:
            return {"found": False, "name": name}
        cols = [d[0] for d in cur.description]
        rec = {c: _jsonable(v) for c, v in zip(cols, row)}
    finally:
        cur.close(); cx.close()
    rec["found"] = True
    return rec


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
