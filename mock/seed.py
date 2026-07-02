"""Mock WMS: a small SQLite database with seeded faults, so the full aiops
loop is runnable by anyone — no real warehouse required.

Schema mirrors the *shape* of a real host-integration layer (generic names):
  host_order_queue : host->WMS order staging (import_status: NULL/I/S/E)
  orders           : the live order table

Seeded faults:
  * 3 imports stuck 'I' (importer died mid-batch 40+ minutes ago)
  * 1 genuine import error ('Invalid Warehouse ID') among benign lock rejections
"""
from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path

HOME = Path(os.getenv("AIOPS_HOME", Path(__file__).resolve().parent.parent))
MOCK_DB = HOME / "mock_wms.sqlite"


def conn() -> sqlite3.Connection:
    return sqlite3.connect(MOCK_DB)


def seed(fresh: bool = True) -> None:
    if fresh and MOCK_DB.exists():
        MOCK_DB.unlink()
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS host_order_queue(
      id INTEGER PRIMARY KEY, order_number TEXT, wh_id TEXT,
      import_status TEXT, error_msg TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS orders(
      order_number TEXT, wh_id TEXT, status TEXT);
    """)
    t = lambda mins: (datetime.datetime.now() - datetime.timedelta(minutes=mins)
                      ).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    # healthy successes
    for i in range(1, 21):
        rows.append((f"5000{i:02d}", "DC-EAST", "S", "", t(120 - i)))
    # benign lock rejections (working as designed)
    rows.append(("500021", "DC-EAST", "E",
                 "Order is already added to wave - cannot make change to this order |", t(30)))
    rows.append(("500022", "DC-EAST", "E",
                 "Picking has started - cannot make changes to this order |", t(25)))
    # the GENUINE error
    rows.append(("500023", "DC-WEST", "E", "Invalid Warehouse ID on Outbound Order |", t(20)))
    # stuck in-progress imports (importer crashed mid-batch)
    for i, o in enumerate(("500031", "500032", "500033")):
        rows.append((o, "DC-EAST", "I", "", t(40 + i)))
    c.executemany("INSERT INTO host_order_queue(order_number, wh_id, import_status, error_msg, created_at) "
                  "VALUES (?,?,?,?,?)", rows)
    # live orders for the successes only
    c.executemany("INSERT INTO orders VALUES (?,?,?)",
                  [(f"5000{i:02d}", "DC-EAST", "N") for i in range(1, 21)])
    c.commit()
    c.close()


if __name__ == "__main__":
    seed()
    print(f"mock WMS seeded: {MOCK_DB}")
