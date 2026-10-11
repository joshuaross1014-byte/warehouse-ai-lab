"""Operations panels: the floor-health questions you ask every morning, one endpoint each."""
from flask import Blueprint, jsonify

import db
from .common import arg, int_arg, jsonerr, profile

bp = Blueprint("ops", __name__, url_prefix="/api/ops")

PANELS = {
    # name: (title, params it accepts)
    "orders_by_status": ("Orders by warehouse / status", ("days", "wh")),
    "waves_by_status": ("Waves by warehouse / status", ("days", "wh")),
    "wave_errors": ("Wave errors", ("hours", "wh")),
    "import_errors": ("Host import errors (non-lock)", ("hours", "wh")),
    "import_queue": ("Host import queue by status", ("hours", "wh")),
    "picks_by_status": ("Picks by status / work type", ("days", "wh")),
    "rf_sessions": ("RF operators active", ("hours", "wh")),
    "open_logons": ("Open RF logons (no logoff)", ("wh",)),
    "tran_activity_today": ("Transaction activity today", ("wh",)),
    "location_status": ("Locations by zone / status", ("wh",)),
    "whse_control": ("t_whse_control switches", ("wh",)),
    "blocking": ("Active / blocking sessions (needs VIEW SERVER STATE)", ()),
    "warehouses": ("Warehouses (item counts)", ()),
}


@bp.get("/panels")
def panels():
    return jsonify([{"name": k, "title": v[0], "params": v[1]} for k, v in PANELS.items()])


@bp.get("/<name>")
@jsonerr
def panel(name: str):
    if name not in PANELS:
        raise KeyError(f"unknown panel '{name}'")
    title, accepted = PANELS[name]
    params = {}
    if "days" in accepted:
        params["days"] = int_arg("days", 7, 1, 3650)
    if "hours" in accepted:
        params["hours"] = int_arg("hours", 24, 1, 24 * 365)
    if "wh" in accepted:
        params["wh"] = arg("wh").upper()
    res = db.named(profile(), name, **params)
    res["title"] = title
    res["params"] = params
    return jsonify(res)
