"""Object browser: procs / views / functions / triggers, body search, dependencies, perf stats."""
from flask import Blueprint, jsonify

import db
from .common import arg, int_arg, jsonerr, like, profile

bp = Blueprint("objects", __name__, url_prefix="/api/objects")


@bp.get("/search")
@jsonerr
def search():
    body = 1 if arg("body") in ("1", "true") else 0
    return jsonify(db.named(profile(), "search", like=like(arg("q")), body=body))


@bp.get("/definition")
@jsonerr
def definition():
    name = arg("name")
    p = profile()
    return jsonify({
        "name": name,
        "definition": db.named(p, "definition", name=name),
        "parameters": db.named(p, "parameters", name=name),
        "deps": db.named(p, "deps", name=name),
    })


@bp.get("/recent")
@jsonerr
def recent():
    return jsonify(db.named(profile(), "recent", days=int_arg("days", 30, 1, 3650)))


@bp.get("/proc_stats")
@jsonerr
def proc_stats():
    return jsonify(db.named(profile(), "proc_stats", like=like(arg("like"))))
