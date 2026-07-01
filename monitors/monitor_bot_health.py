"""Monitor: RPA bot-fleet health (Automation Anywhere A360-style control room).

Alerts (last 24h) on: any bot whose failure RATE exceeds a threshold (with a
minimum run count and a minimum failure floor so a single blip doesn't page),
any run stuck IN_PROGRESS > 4h, and any bot that ran on a schedule earlier but
has gone silent > 24h. Silent when clean. Intended to run once daily.

Tune: MONITOR_BOT_FAILRATE (default 0.10), MONITOR_BOT_MINRUNS (5), MONITOR_BOT_MINFAILS (2).
"""
import collections
import datetime as dt
import os

import monitor_common as mc
import robo_connect

MONITOR = "bot_health"
FAILRATE = float(os.getenv("MONITOR_BOT_FAILRATE", "0.10"))
MINRUNS = int(os.getenv("MONITOR_BOT_MINRUNS", "5"))
MINFAILS = int(os.getenv("MONITOR_BOT_MINFAILS", "2"))
FAIL = {"RUN_FAILED", "DEPLOY_FAILED", "RUN_TIMED_OUT", "RUN_ABORTED"}
STUCK_HOURS = 4


def fetch(sess, base, start, end):
    out, offset = [], 0
    while True:
        body = {"sort": [{"field": "startDateTime", "direction": "asc"}],
                "filter": {"operator": "and", "operands": [
                    {"operator": "ge", "field": "startDateTime", "value": start},
                    {"operator": "le", "field": "startDateTime", "value": end}]},
                "page": {"offset": offset, "length": 200}}
        r = sess.post(base + "/v3/activity/list", json=body, timeout=60)
        r.raise_for_status()
        d = r.json()
        rows = d.get("list", [])
        out.extend(rows)
        total = (d.get("page") or {}).get("totalFilter", len(out))
        offset += len(rows)
        if not rows or offset >= total:
            break
    return out


def main() -> int:
    end = mc.now_utc()
    start = end - dt.timedelta(hours=24)
    sess, base = robo_connect.get_session()
    acts = fetch(sess, base,
                 start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                 end.strftime("%Y-%m-%dT%H:%M:%S.999Z"))

    per = collections.defaultdict(lambda: {"runs": 0, "fails": 0, "sched": 0, "last": None})
    stuck = []
    for a in acts:
        fn = a.get("fileName") or "?"
        p = per[fn]
        p["runs"] += 1
        st = a.get("status")
        if st in FAIL:
            p["fails"] += 1
        if a.get("type") == "SCHEDULED":
            p["sched"] += 1
        sdt = a.get("startDateTime")
        p["last"] = sdt if p["last"] is None else max(p["last"], sdt)
        if st == "IN_PROGRESS" and sdt:
            try:
                started = dt.datetime.fromisoformat(sdt.replace("Z", "+00:00"))
                if (end - started).total_seconds() > STUCK_HOURS * 3600:
                    stuck.append((fn, sdt))
            except ValueError:
                pass

    lines = []
    for fn, p in sorted(per.items(), key=lambda kv: -kv[1]["fails"]):
        if p["runs"] >= MINRUNS and p["fails"] >= MINFAILS and p["fails"] / p["runs"] > FAILRATE:
            lines.append(f"{fn}: {p['fails']}/{p['runs']} failed ({p['fails']/p['runs']:.0%})")
    for fn, sdt in stuck:
        lines.append(f"STUCK IN_PROGRESS > {STUCK_HOURS}h: {fn} (since {sdt[:19]})")

    cutoff = (end - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    for fn, p in per.items():
        if p["sched"] > 0 and (p["last"] or "") < cutoff:
            lines.append(f"SCHEDULED BUT SILENT > 24h: {fn} (last {str(p['last'])[:19]})")

    if lines:
        mc.slack_alert(MONITOR, "RPA bot fleet — last 24h", lines)
        return 1

    mc.heartbeat(MONITOR, f"{len(acts)} runs / {len(per)} bots, no rate breaches/stuck/silent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
