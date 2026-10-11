"""Schema explorer: tables, columns, indexes, FKs, triggers, column search, sample rows."""
from flask import Blueprint, jsonify

import db
from .common import arg, int_arg, jsonerr, like, profile

bp = Blueprint("schema", __name__, url_prefix="/api/schema")


@bp.get("/tables")
@jsonerr
def tables():
    return jsonify(db.named(profile(), "tables", like=like(arg("like"))))


@bp.get("/views")
@jsonerr
def views():
    return jsonify(db.named(profile(), "views", like=like(arg("like"))))


@bp.get("/table")
@jsonerr
def table():
    name = arg("name")
    p = profile()
    return jsonify({
        "name": name,
        "columns": db.named(p, "columns", table=name),
        "indexes": db.named(p, "indexes", table=name),
        "foreign_keys": db.named(p, "foreign_keys", table=name),
        "triggers": db.named(p, "triggers", table=name),
        "used_by": db.named(p, "used_by", name=name),
    })


@bp.get("/sample")
@jsonerr
def sample():
    name = arg("name")
    n = int_arg("n", 50, 1, 500)
    if not name.replace("_", "").replace(".", "").isalnum():
        raise KeyError("bad table name")
    sql = f"SELECT TOP {n} * FROM {name} WITH (NOLOCK)"
    return jsonify(db.run_query(profile(), sql))


@bp.get("/find_column")
@jsonerr
def find_column():
    return jsonify(db.named(profile(), "find_column", like=like(arg("like"))))
