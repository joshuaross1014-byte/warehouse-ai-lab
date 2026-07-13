"""Playbook: host order imports stuck in-progress.

An importer that dies mid-batch leaves rows in import_status='I' forever; the
orders never reach the floor and nobody gets an error. Classic silent failure.

Remediation is the standard operator fix — reset the stuck rows to NULL so the
next import cycle retries them — proposed as exact SQL with a verification
contract, and executed only after human approval.
"""
from __future__ import annotations

TYPE = "stuck_import"
SEVERITY = "critical"
STUCK_MIN = 15


def detect(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, order_number, wh_id, created_at FROM host_order_queue "
        "WHERE import_status='I' AND created_at < datetime('now', 'localtime', ?)",
        (f"-{STUCK_MIN} minutes",)).fetchall()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    return [{
        "fingerprint": f"{TYPE}:{min(ids)}-{max(ids)}",
        "summary": f"{len(rows)} order import(s) stuck in-progress > {STUCK_MIN} min",
        "evidence": {"rows": [{"id": r[0], "order": r[1], "wh": r[2], "since": r[3]}
                              for r in rows]},
    }]


def diagnose(conn, evidence: dict) -> dict:
    rows = evidence["rows"]
    # corroborate: none of these orders made it to the live order table
    landed = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE order_number IN (%s)"
        % ",".join("?" * len(rows)), [r["order"] for r in rows]).fetchone()[0]
    return {
        "root_cause": "importer terminated mid-batch, leaving rows claimed ('I') but never finished",
        "corroboration": f"{landed}/{len(rows)} of the stuck orders reached the live order table",
        "blast_radius": f"{len(rows)} orders invisible to the floor until re-imported",
    }


def propose(conn, diagnosis: dict, evidence: dict) -> dict:
    ids = [r["id"] for r in evidence["rows"]]
    id_list = ",".join(str(i) for i in ids)
    return {
        "kind": "sql_fix",
        "summary": f"Reset {len(ids)} stuck row(s) to NULL so the next import cycle retries them",
        "sql": [f"UPDATE host_order_queue SET import_status=NULL "
                f"WHERE id IN ({id_list}) AND import_status='I'"],
        "verify": {
            "query": f"SELECT COUNT(*) FROM host_order_queue "
                     f"WHERE id IN ({id_list}) AND import_status='I'",
            "expect": 0,
            "meaning": "no targeted rows remain stuck after the fix",
        },
        "risk": "Low — resets only the targeted claimed rows; the importer treats NULL as pending "
                "and re-processes idempotently. No data is deleted.",
    }
