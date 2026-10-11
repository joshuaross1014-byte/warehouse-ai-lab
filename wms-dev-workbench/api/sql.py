"""
Ad-hoc SQL tab: run one guarded statement, keep a local history, save favourites.

History and saved queries live in workbench.sqlite next to app.py (never in WMS).
"""
from __future__ import annotations

import sqlite3
import time

from flask import Blueprint, jsonify, request

import config
import db
from .common import int_arg, jsonerr, profile

bp = Blueprint("sql", __name__, url_prefix="/api/sql")


def _state() -> sqlite3.Connection:
    con = sqlite3.connect(config.STATE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY, ts REAL, profile TEXT, sql TEXT, kind TEXT,
        rowcount INTEGER, ms INTEGER, error TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS saved (
        name TEXT PRIMARY KEY, sql TEXT, note TEXT, updated REAL)""")
    return con


@bp.post("/run")
@jsonerr
def run():
    body = request.get_json(force=True) or {}
    sql = (body.get("sql") or "").strip()
    p = config.get_profile(body.get("profile") or request.args.get("profile")).name
    max_rows = int(body.get("max_rows") or int_arg("max_rows", config.MAX_ROWS_DEFAULT))
    allow_write = bool(body.get("allow_write"))
    con = _state()
    try:
        res = db.run_query(p, sql, max_rows=max_rows, allow_write=allow_write)
        con.execute("INSERT INTO history(ts,profile,sql,kind,rowcount,ms,error) VALUES (?,?,?,?,?,?,NULL)",
                    (time.time(), p, sql, res["kind"], res["rowcount"], res["ms"]))
        con.commit()
        return jsonify(res)
    except Exception as e:
        con.execute("INSERT INTO history(ts,profile,sql,kind,rowcount,ms,error) VALUES (?,?,?,?,?,?,?)",
                    (time.time(), p, sql, "error", 0, 0, str(e)[:500]))
        con.commit()
        raise
    finally:
        con.close()


@bp.get("/history")
@jsonerr
def history():
    con = _state()
    rows = con.execute(
        "SELECT id, ts, profile, sql, kind, rowcount, ms, error FROM history ORDER BY id DESC LIMIT ?",
        (int_arg("n", 50, 1, 500),)).fetchall()
    con.close()
    return jsonify([dict(zip(("id", "ts", "profile", "sql", "kind", "rowcount", "ms", "error"), r)) for r in rows])


@bp.get("/saved")
@jsonerr
def saved_list():
    con = _state()
    rows = con.execute("SELECT name, sql, note, updated FROM saved ORDER BY name").fetchall()
    con.close()
    return jsonify([dict(zip(("name", "sql", "note", "updated"), r)) for r in rows])


@bp.post("/saved")
@jsonerr
def saved_put():
    body = request.get_json(force=True) or {}
    name, sql = (body.get("name") or "").strip(), (body.get("sql") or "").strip()
    if not name or not sql:
        raise KeyError("name and sql are required")
    con = _state()
    con.execute("INSERT INTO saved(name,sql,note,updated) VALUES (?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET sql=excluded.sql, note=excluded.note, updated=excluded.updated",
                (name, sql, body.get("note") or "", time.time()))
    con.commit()
    con.close()
    return jsonify({"ok": True, "name": name})


@bp.delete("/saved")
@jsonerr
def saved_delete():
    name = (request.args.get("name") or "").strip()
    con = _state()
    con.execute("DELETE FROM saved WHERE name = ?", (name,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@bp.get("/library")
@jsonerr
def library():
    """The named queries shipped in queries/*.sql, so you can read and reuse them."""
    return jsonify({k: v for k, v in sorted(db.load_queries().items())})


@bp.get("/profiles")
def profiles():
    return jsonify([
        {"name": p.name, "server": p.server, "database": p.database,
         "writable": p.writable, "color": p.color}
        for p in config.PROFILES.values()
    ] + [{"default": config.DEFAULT_PROFILE}])
