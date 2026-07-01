"""Monitor: regional price-list propagation gap (SAP B1).

In a multi-region B1 setup, each region prices off its own "base" price list that
is COPIED from a source list by an external/scheduled job. If that copy lags, new
orders for the region import with blank unit prices. For each region this counts
items priced in its SOURCE list but blank in the REGION list, alerts if any gap
exceeds a threshold, and reports the day-over-day delta so a growing gap stands
out from a chronic baseline.

Run once each morning BEFORE the regional order import, so the copy job can be
pushed if it is behind.

Configure REGIONS and MONITOR_PRICEGAP_THRESHOLD (default 1000) for your topology.
"""
import json
import os
from pathlib import Path

import monitor_common as mc
import hana_connect

MONITOR = "so_price_gap"
THRESHOLD = int(os.getenv("MONITOR_PRICEGAP_THRESHOLD", "1000"))
STATE = Path(__file__).with_name("so_price_gap_state.json")

# (label, region_list_num, source_list_num). Each regional list may copy from a
# different source (the base list, or a sublist). EXAMPLE values — replace with
# your own OPLN topology (query OPLN.U_BasePriceList to find each region's source).
REGIONS = [
    ("REGION_1", 20, 1),
    ("REGION_2", 30, 1),
    ("REGION_3", 40, 5),
]

# Unqualified table names resolve to ERP_HANA_SCHEMA (set in .env).
GAP_SQL = """
WITH s AS (SELECT "ItemCode" FROM "ITM1" WHERE "PriceList"=? AND "Price">0),
     r AS (SELECT "ItemCode" FROM "ITM1" WHERE "PriceList"=? AND "Price">0)
SELECT (SELECT COUNT(*) FROM s WHERE "ItemCode" NOT IN (SELECT "ItemCode" FROM r)) FROM DUMMY
"""


def main() -> int:
    conn = hana_connect.get_connection()
    cur = conn.cursor()
    gaps = {}
    for lbl, reg, src in REGIONS:
        cur.execute(GAP_SQL, (src, reg))
        gaps[lbl] = int(cur.fetchone()[0])
    cur.close()
    conn.close()

    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text()).get("gaps", {})
        except Exception:  # noqa: BLE001
            prev = {}

    breaches = []
    for lbl, reg, src in REGIONS:
        g = gaps[lbl]
        if g > THRESHOLD:
            d = g - prev.get(lbl, g)
            delta = f"{'+' if d >= 0 else ''}{d} since last run" if prev else "no prior baseline"
            breaches.append(f"{lbl} (#{reg}<-#{src}): {g} items blank — {delta}")

    STATE.write_text(json.dumps({"ts": mc.now_utc().isoformat(), "gaps": gaps}))

    if breaches:
        mc.slack_alert(MONITOR, f"Price-gap before regional import (threshold {THRESHOLD})",
                       breaches + ["Push the source->region price-list copy job before the import."])
        return 1

    mc.heartbeat(MONITOR, "all regions under threshold: " + ", ".join(f"{k}={v}" for k, v in gaps.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
