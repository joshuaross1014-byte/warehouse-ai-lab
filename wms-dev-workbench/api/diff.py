"""
Diff: compare object definitions between two profiles (PROD vs TEST).

This is the question you ask after every deploy and every restore:
"is what runs on PROD the same text as what we tested on TEST?"
"""
from __future__ import annotations

import difflib

from flask import Blueprint, jsonify

import config
import db
from .common import arg, jsonerr, like

bp = Blueprint("diff", __name__, url_prefix="/api/diff")


def _definition(profile: str, name: str) -> str:
    res = db.named(profile, "definition", name=name)
    if not res["rows"]:
        return ""
    return res["rows"][0][res["columns"].index("definition")] or ""


@bp.get("/object")
@jsonerr
def object_diff():
    name = arg("name")
    left = config.get_profile(arg("left", "PROD")).name
    right = config.get_profile(arg("right", "TEST")).name
    a, b = _definition(left, name), _definition(right, name)
    lines = list(difflib.unified_diff(
        a.splitlines(), b.splitlines(), fromfile=f"{left}:{name}", tofile=f"{right}:{name}", lineterm="", n=3))
    return jsonify({
        "name": name, "left": left, "right": right,
        "left_exists": bool(a), "right_exists": bool(b),
        "same": a == b and bool(a),
        "diff": lines,
        "left_len": len(a), "right_len": len(b),
    })


@bp.get("/bulk")
@jsonerr
def bulk():
    pattern = like(arg("like"))
    left = config.get_profile(arg("left", "PROD")).name
    right = config.get_profile(arg("right", "TEST")).name
    la = db.named(left, "hash_list", like=pattern)
    ra = db.named(right, "hash_list", like=pattern)

    def index(res):
        c = res["columns"]
        return {r[c.index("name")]: {"hash": r[c.index("def_hash")], "type": r[c.index("type_desc")],
                                      "modified": r[c.index("modify_date")], "len": r[c.index("def_len")]}
                for r in res["rows"]}

    L, R = index(la), index(ra)
    rows = []
    for name in sorted(set(L) | set(R)):
        l, r = L.get(name), R.get(name)
        status = ("same" if l and r and l["hash"] == r["hash"]
                  else "differs" if l and r
                  else f"{left} only" if l else f"{right} only")
        rows.append([name, (l or r)["type"], status,
                     l["modified"] if l else None, r["modified"] if r else None,
                     l["len"] if l else None, r["len"] if r else None])
    return jsonify({
        "columns": ["name", "type", "status", f"{left}_modified", f"{right}_modified", f"{left}_len", f"{right}_len"],
        "rows": rows, "rowcount": len(rows), "truncated": False,
        "ms": la["ms"] + ra["ms"], "left": left, "right": right,
        "summary": {k: sum(1 for r in rows if r[2] == k) for k in ("same", "differs", f"{left} only", f"{right} only")},
    })
