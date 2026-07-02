"""Incident store (SQLite, stdlib-only) + runbook appender."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import Incident, OPEN_STATES, now

HOME = Path(os.getenv("AIOPS_HOME", Path(__file__).resolve().parent.parent))
STATE_DB = HOME / "aiops_state.sqlite"
RUNBOOK = HOME / "runbook.md"

_SCHEMA = """CREATE TABLE IF NOT EXISTS incidents (
  iid TEXT PRIMARY KEY, itype TEXT, severity TEXT, summary TEXT, fingerprint TEXT,
  state TEXT, created_at TEXT, updated_at TEXT,
  evidence TEXT, diagnosis TEXT, proposal TEXT, execution TEXT, verification TEXT,
  resolution TEXT)"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(STATE_DB)
    c.execute(_SCHEMA)
    return c


def next_id() -> str:
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    return f"INC-{n + 1:04d}"


def save(inc: Incident) -> None:
    inc.touch()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  inc.to_row())


def get(iid: str) -> Incident | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM incidents WHERE iid=?", (iid,)).fetchone()
    return Incident.from_row(r) if r else None


def all_incidents(state: str | None = None) -> list[Incident]:
    q, args = "SELECT * FROM incidents", ()
    if state:
        q, args = q + " WHERE state=?", (state,)
    with _conn() as c:
        return [Incident.from_row(r) for r in c.execute(q + " ORDER BY iid", args)]


def open_fingerprints() -> set[str]:
    with _conn() as c:
        rows = c.execute("SELECT fingerprint FROM incidents WHERE state IN (%s)"
                         % ",".join("?" * len(OPEN_STATES)), tuple(OPEN_STATES))
        return {r[0] for r in rows}


def runbook_append(inc: Incident, outcome: str) -> None:
    """The organizational memory: every closed incident becomes a runbook entry
    future diagnoses (human or AI) can learn from."""
    entry = (f"\n## {inc.iid} — {inc.itype} — {outcome} ({now()})\n"
             f"- **Summary:** {inc.summary}\n"
             f"- **Root cause:** {inc.diagnosis.get('root_cause', 'n/a')}\n"
             f"- **Action:** {inc.proposal.get('summary', 'n/a')}\n"
             f"- **Resolution:** {inc.resolution}\n")
    with open(RUNBOOK, "a", encoding="utf-8") as f:
        f.write(entry)
