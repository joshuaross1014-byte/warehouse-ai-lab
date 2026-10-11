"""
Trace: follow one business key through every table that touches it.

Each trace is a list of sections; the UI renders them top-down as a story:
host record -> order -> lines -> waves -> picks -> HUs -> transaction log.
Add a new trace by appending to TRACES and the matching blocks in queries/trace.sql.
"""
from flask import Blueprint, jsonify

import db
from .common import arg, jsonerr, profile

bp = Blueprint("trace", __name__, url_prefix="/api/trace")

# kind -> [(section title, query name, needs_wh)]
TRACES = {
    "order": [
        ("Host import records (t_al_host_order_master)", "order_host", False),
        ("Order header (t_order)", "order_header", True),
        ("Order lines (t_order_detail)", "order_lines", True),
        ("Waves (t_wave_master)", "order_waves", True),
        ("Picks (t_pick_detail)", "order_picks", True),
        ("Handling units (t_hu_master)", "order_hus", False),
        ("Transaction log (t_tran_log, newest first)", "order_tranlog", False),
    ],
    "item": [
        ("Item master by warehouse (t_item_master)", "item_master", False),
        ("UOMs (t_item_uom)", "item_uom", True),
        ("On-hand by location (t_stored_item)", "item_stock", True),
        ("Picks, last 14 days (t_pick_detail)", "item_picks", True),
        ("Transaction log, last 7 days (t_tran_log)", "item_tranlog", True),
    ],
    "hu": [
        ("HU master (t_hu_master)", "hu_master", False),
        ("Contents (t_stored_item)", "hu_contents", False),
        ("Transaction log (t_tran_log)", "hu_tranlog", False),
    ],
    "po": [
        ("PO header (t_po_master)", "po_master", False),
        ("PO lines (t_po_detail)", "po_lines", True),
        ("Receipts (t_receipt)", "po_receipts", True),
        ("Transaction log (t_tran_log)", "po_tranlog", False),
    ],
    "wave": [
        ("Wave (t_wave_master)", "wave_master", False),
        ("Orders in wave, pick rollup (t_pick_detail)", "wave_orders", False),
        ("Wave errors (t_log_wave_error)", "wave_error_log", False),
        ("Autorelease log (t_autorelease_log)", "wave_autorelease", False),
    ],
    "employee": [
        ("Operator (t_employee)", "emp_master", False),
        ("Logons (t_employee_logon)", "emp_logons", False),
        ("Transaction log (t_tran_log)", "emp_tranlog", False),
    ],
    "location": [
        ("Location (t_location)", "loc_master", True),
        ("Contents (t_stored_item)", "loc_stock", True),
        ("Transaction log, last 7 days (t_tran_log)", "loc_tranlog", True),
    ],
}


@bp.get("/kinds")
def kinds():
    return jsonify(sorted(TRACES))


@bp.get("/<kind>")
@jsonerr
def trace(kind: str):
    if kind not in TRACES:
        raise KeyError(f"unknown trace kind '{kind}'")
    n, wh, p = arg("n"), arg("wh").upper(), profile()
    if not n:
        raise KeyError("n (the key) is required")
    sections = []
    for title, qname, needs_wh in TRACES[kind]:
        params = {"n": n, "wh": wh} if needs_wh else {"n": n}
        try:
            res = db.named(p, qname, **params)
        except Exception as e:  # one missing table must not kill the whole trace
            res = {"error": str(e).splitlines()[0][:300], "columns": [], "rows": [], "query": qname}
        sections.append({"title": title, "result": res})
    return jsonify({"kind": kind, "key": n, "wh": wh, "profile": p, "sections": sections})
