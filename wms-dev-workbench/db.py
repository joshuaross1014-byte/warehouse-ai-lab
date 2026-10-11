"""
db.py - connection layer.

One lazily-created SQLAlchemy engine per profile (same singleton pattern that
fixed the MCP servers' cold-start cost in Aug 2026), pyodbc underneath, with
pool_pre_ping + pool_recycle so a firewall idle-kill never surfaces as an error.

run_query() is the only way the API layer talks to SQL Server:
    guard -> bind parameters -> per-call query timeout -> fetch max_rows+1
    -> JSON-safe rows -> timing.
Named queries live in queries/*.sql as `-- name: xxx` blocks (see load_queries).
"""
from __future__ import annotations

import datetime as dt
import decimal
import time
import urllib.parse
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import config
import guard

_engines: dict[str, Engine] = {}


def get_engine(profile_name: str) -> Engine:
    profile = config.get_profile(profile_name)
    eng = _engines.get(profile.name)
    if eng is None:
        user, pwd = profile.credentials()
        # Build the ODBC string with the password URL-quoted: special characters
        # in passwords were a classic first-day setup failure.
        odbc = (
            f"Driver={{{config.DRIVER}}};"
            f"Server={profile.server};"
            f"Database={profile.database};"
            f"UID={user};PWD={pwd};"
            "TrustServerCertificate=yes;Encrypt=yes;"
            f"APP=wms_dev_workbench;"
        )
        url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc)
        eng = create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)
        _engines[profile.name] = eng
    return eng


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (dt.datetime,)):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "0x" + bytes(v).hex()
    return str(v)


def run_query(
    profile_name: str,
    sql: str,
    params: dict | None = None,
    max_rows: int | None = None,
    allow_write: bool = False,
    timeout: int | None = None,
) -> dict:
    profile = config.get_profile(profile_name)
    kind = guard.check(sql, profile, allow_write=allow_write)
    cap = min(max_rows or config.MAX_ROWS_DEFAULT, config.MAX_ROWS_HARD_CAP)
    eng = get_engine(profile.name)
    t0 = time.perf_counter()
    with eng.connect() as conn:
        try:  # per-statement timeout on the raw pyodbc connection
            conn.connection.dbapi_connection.timeout = timeout or config.QUERY_TIMEOUT
        except Exception:
            pass
        result = conn.execute(text(sql), params or {})
        if result.returns_rows:
            columns = list(result.keys())
            raw = result.fetchmany(cap + 1)
            truncated = len(raw) > cap
            rows = [[_jsonable(v) for v in r] for r in raw[:cap]]
            rowcount = len(rows)
        else:
            columns, rows, truncated, rowcount = [], [], False, result.rowcount
            if kind == "write":
                conn.commit()
    ms = round((time.perf_counter() - t0) * 1000)
    return {
        "profile": profile.name,
        "kind": kind,
        "columns": columns,
        "rows": rows,
        "rowcount": rowcount,
        "truncated": truncated,
        "ms": ms,
    }


# ---- named query library ----------------------------------------------------
_QUERIES: dict[str, str] = {}


def load_queries(folder: Path = config.QUERIES_DIR) -> dict[str, str]:
    """Parse every queries/*.sql into {name: sql}. Blocks start with `-- name: xxx`."""
    found: dict[str, str] = {}
    for path in sorted(folder.glob("*.sql")):
        name, buf = None, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("-- name:"):
                if name:
                    found[name] = "\n".join(buf).strip()
                name, buf = line.split(":", 1)[1].strip(), []
            else:
                buf.append(line)
        if name:
            found[name] = "\n".join(buf).strip()
    _QUERIES.clear()
    _QUERIES.update(found)
    return found


def q(name: str) -> str:
    if not _QUERIES:
        load_queries()
    try:
        return _QUERIES[name]
    except KeyError:
        raise KeyError(f"No query named '{name}' in {config.QUERIES_DIR}")


def named(profile: str, qname: str, /, **params) -> dict:
    """Run a named query. qname is positional-only so a bound parameter may be called name."""
    res = run_query(profile, q(qname), params)
    res["query"] = qname
    return res
