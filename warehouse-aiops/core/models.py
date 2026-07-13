r"""Incident model and lifecycle states.

The state machine is the safety model:

    PROPOSED --(human approve, sql_fix)--> EXECUTED -> VERIFIED / FAILED(rolled back)
    PROPOSED --(human approve, manual)---> ACKNOWLEDGED -> CLOSED (auto, once cleared)
    PROPOSED --(human reject)------------> REJECTED

Nothing moves past PROPOSED without a human. Proposals are *data* (the exact
SQL / steps + a verification contract), never actions. ACKNOWLEDGED incidents
stay open for dedup (no re-alerting) and auto-close when a later scan finds
the underlying condition gone.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field, asdict

DETECTED = "DETECTED"
PROPOSED = "PROPOSED"
APPROVED = "APPROVED"
ACKNOWLEDGED = "ACKNOWLEDGED"
REJECTED = "REJECTED"
EXECUTED = "EXECUTED"
VERIFIED = "VERIFIED"
FAILED = "FAILED"
CLOSED = "CLOSED"

OPEN_STATES = {DETECTED, PROPOSED, APPROVED, ACKNOWLEDGED, EXECUTED, FAILED}


def now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%SZ")


@dataclass
class Incident:
    iid: str
    itype: str                 # playbook type key
    severity: str              # info | warning | critical
    summary: str
    fingerprint: str           # dedup key: same fault -> same open incident
    state: str = PROPOSED
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    evidence: dict = field(default_factory=dict)      # what the detector saw
    diagnosis: dict = field(default_factory=dict)     # root-cause classification
    proposal: dict = field(default_factory=dict)      # kind, steps/sql, verify, risk
    execution: dict = field(default_factory=dict)     # what actually ran
    verification: dict = field(default_factory=dict)  # read-back result
    resolution: str = ""

    def touch(self):
        self.updated_at = now()

    def to_row(self) -> tuple:
        return (self.iid, self.itype, self.severity, self.summary, self.fingerprint,
                self.state, self.created_at, self.updated_at,
                json.dumps(self.evidence), json.dumps(self.diagnosis),
                json.dumps(self.proposal), json.dumps(self.execution),
                json.dumps(self.verification), self.resolution)

    @classmethod
    def from_row(cls, r) -> "Incident":
        return cls(iid=r[0], itype=r[1], severity=r[2], summary=r[3], fingerprint=r[4],
                   state=r[5], created_at=r[6], updated_at=r[7],
                   evidence=json.loads(r[8]), diagnosis=json.loads(r[9]),
                   proposal=json.loads(r[10]), execution=json.loads(r[11]),
                   verification=json.loads(r[12]), resolution=r[13])

    def brief(self) -> dict:
        return {"id": self.iid, "type": self.itype, "severity": self.severity,
                "state": self.state, "summary": self.summary, "created": self.created_at}

    def full(self) -> dict:
        return asdict(self)
