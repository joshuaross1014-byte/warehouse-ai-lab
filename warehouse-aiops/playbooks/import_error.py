"""Playbook: genuine host order import errors.

Error-status rows are dominated by BENIGN rejections (the WMS correctly
refusing to change an order already being picked/waved). A real failure hides
among them — often concatenated with benign text — so detection strips the
known-benign phrases and alerts only on the residual.

Deliberately proposes a MANUAL action: a bad warehouse/customer/item mapping is
a data problem upstream — auto-"fixing" it would hide the root cause. Knowing
what NOT to automate is part of the safety model.
"""
from __future__ import annotations

TYPE = "import_error"
SEVERITY = "warning"

BENIGN = [
    "Picking has started - cannot make changes to this order",
    "Order is already added to wave - cannot make change to this order",
    "Order is being allocated - cannot make changes to this order",
]


def _residual(msg: str) -> str:
    for phrase in BENIGN:
        msg = msg.replace(phrase, "")
    return msg.replace("|", "").strip()


def detect(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, order_number, wh_id, error_msg, created_at "
        "FROM host_order_queue WHERE import_status='E'").fetchall()
    real = [(r, _residual(r[3])) for r in rows]
    real = [(r, res) for r, res in real if res]
    if not real:
        return []
    findings = []
    for r, res in real:
        findings.append({
            "fingerprint": f"{TYPE}:{r[0]}",
            "summary": f"Order {r[1]} failed import: {res}",
            "evidence": {"row_id": r[0], "order": r[1], "wh": r[2],
                         "error": res, "full_msg": r[3], "since": r[4]},
        })
    return findings


def diagnose(conn, evidence: dict) -> dict:
    err = evidence["error"].lower()
    if "warehouse" in err:
        cause = "order references a warehouse not configured in the WMS (host->WMS mapping gap)"
        fix_at = "fix the warehouse mapping in the host system, then re-export the order"
    elif "item" in err:
        cause = "item not synced to the target warehouse (master-data gate not set)"
        fix_at = "fix the item's sync flags in the host system, then re-export"
    elif "customer" in err:
        cause = "customer missing from the WMS customer master"
        fix_at = "sync the customer master, then re-export"
    else:
        cause = "unclassified import rejection"
        fix_at = "review the full error and the order's detail rows"
    return {"root_cause": cause, "recommended_path": fix_at,
            "note": "benign lock rejections were filtered out; this is a genuine failure"}


def propose(conn, diagnosis: dict, evidence: dict) -> dict:
    return {
        "kind": "manual",
        "summary": f"Manual data fix required for order {evidence['order']}: "
                   f"{diagnosis['recommended_path']}",
        "sql": [],
        "verify": {"query": None, "expect": None,
                   "meaning": "verified when the order re-imports with status S"},
        "risk": "None from this system — no automated change is safe here; the root cause is "
                "upstream master data. Auto-'fixing' would mask it.",
    }
