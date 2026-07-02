"""The aiops loop: scan -> diagnose -> propose -> (human) approve -> execute -> verify.

Safety model, enforced here:
  * detect/diagnose/propose are READ-ONLY against the warehouse DB
  * a proposal is data (exact SQL + verification contract), never an action
  * execution happens ONLY on explicit human approval, inside a transaction,
    and is immediately verified by read-back; failure rolls back
  * every outcome is appended to the runbook (the organizational memory)
"""
from __future__ import annotations

from . import store
from .models import (Incident, PROPOSED, APPROVED, ACKNOWLEDGED, REJECTED,
                     EXECUTED, VERIFIED, FAILED, CLOSED)

from playbooks import PLAYBOOKS
from mock.seed import conn as wms_conn


def scan() -> list[Incident]:
    """Run every playbook's detector; open one incident per new fingerprint,
    fully diagnosed with a remediation proposal attached."""
    created: list[Incident] = []
    seen = store.open_fingerprints()
    current_fps: set[str] = set()
    c = wms_conn()
    try:
        for pb in PLAYBOOKS:
            for f in pb.detect(c):
                current_fps.add(f["fingerprint"])
                if f["fingerprint"] in seen:
                    continue
                diagnosis = pb.diagnose(c, f["evidence"])
                proposal = pb.propose(c, diagnosis, f["evidence"])
                inc = Incident(iid=store.next_id(), itype=pb.TYPE, severity=pb.SEVERITY,
                               summary=f["summary"], fingerprint=f["fingerprint"],
                               state=PROPOSED, evidence=f["evidence"],
                               diagnosis=diagnosis, proposal=proposal)
                store.save(inc)
                created.append(inc)
                seen.add(f["fingerprint"])
    finally:
        c.close()
    # auto-close ACKNOWLEDGED incidents whose underlying condition has cleared
    for inc in store.all_incidents(ACKNOWLEDGED):
        if inc.fingerprint not in current_fps:
            inc.state = CLOSED
            inc.resolution += " | auto-closed: underlying condition no longer detected"
            store.save(inc)
            store.runbook_append(inc, "CLOSED (condition cleared)")
    return created


def approve(iid: str, operator: str = "operator") -> Incident:
    inc = store.get(iid)
    if inc is None:
        raise KeyError(f"no such incident: {iid}")
    if inc.state != PROPOSED:
        raise ValueError(f"{iid} is {inc.state}; only PROPOSED incidents can be approved")

    inc.state = APPROVED
    inc.execution = {"approved_by": operator}

    if inc.proposal["kind"] == "manual":
        # stays open (no re-alerting) until a scan confirms the fix landed upstream
        inc.state = ACKNOWLEDGED
        inc.resolution = f"manual action acknowledged by {operator}: {inc.proposal['summary']}"
        store.save(inc)
        store.runbook_append(inc, "ACKNOWLEDGED (manual)")
        return inc

    # sql_fix: execute transactionally, then verify by read-back
    c = wms_conn()
    try:
        cur = c.cursor()
        affected = []
        for stmt in inc.proposal["sql"]:
            cur.execute(stmt)
            affected.append(cur.rowcount)
        v = inc.proposal["verify"]
        actual = cur.execute(v["query"]).fetchone()[0]
        if actual == v["expect"]:
            c.commit()
            inc.state = VERIFIED
            inc.execution.update({"statements": inc.proposal["sql"], "rows_affected": affected})
            inc.verification = {"query": v["query"], "expected": v["expect"],
                                "actual": actual, "passed": True}
            inc.resolution = f"fix executed and verified ({sum(affected)} row(s) affected)"
            outcome = "RESOLVED (verified)"
        else:
            c.rollback()
            inc.state = FAILED
            inc.verification = {"query": v["query"], "expected": v["expect"],
                                "actual": actual, "passed": False}
            inc.resolution = "verification failed — transaction rolled back, no change committed"
            outcome = "FAILED (rolled back)"
    finally:
        c.close()
    store.save(inc)
    store.runbook_append(inc, outcome)
    return inc


def reject(iid: str, reason: str = "", operator: str = "operator") -> Incident:
    inc = store.get(iid)
    if inc is None:
        raise KeyError(f"no such incident: {iid}")
    if inc.state != PROPOSED:
        raise ValueError(f"{iid} is {inc.state}; only PROPOSED incidents can be rejected")
    inc.state = REJECTED
    inc.resolution = f"rejected by {operator}: {reason or 'no reason given'}"
    store.save(inc)
    store.runbook_append(inc, "REJECTED")
    return inc
