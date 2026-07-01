"""Monitor: WMS host-order import failures (real, non-benign) + stuck imports.

The host->WMS order staging table accumulates 'E' (error) rows, but most are
BENIGN: once an order is being allocated/waved/picked, the WMS correctly refuses
a re-sync from the host, which is logged as an error. A real failure is often
*concatenated* with a benign message in the same error text, so a simple
NOT IN (benign list) filter misses it. This check STRIPS the known-benign phrases
and alerts only on the residual — plus any import stuck in-progress > 15 min.

Silent when clean. Intended to run hourly under Task Scheduler.
"""
import monitor_common as mc
import wms_connect

MONITOR = "wms_import_errors"
WINDOW_MIN = 90  # look-back; hourly run with overlap so nothing is missed

# Product-standard benign rejection phrases (WMS refuses to re-sync a live order).
REAL_ERRORS_SQL = f"""
;WITH e AS (
  SELECT display_order_number, wh_id, customer_code, record_create_date,
    residual = LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(REPLACE(error_msg,
        'Picking has started - cannot make changes to this order',''),
        'Order is already added to wave - cannot make change to this order',''),
        'Order is being allocated - cannot make changes to this order',''),
      '|','')))
  FROM dbo.t_al_host_order_master WITH (NOLOCK)
  WHERE import_status='E'
    AND record_create_date >= DATEADD(minute, -{WINDOW_MIN}, GETDATE())
)
SELECT residual AS real_error, COUNT(*) AS cnt, MAX(record_create_date) AS last_seen,
       MAX(wh_id) AS a_wh, MAX(display_order_number) AS an_order
FROM e WHERE LEN(residual) > 0
GROUP BY residual ORDER BY cnt DESC;
"""

STUCK_SQL = """
SELECT COUNT(*) AS stuck_in_progress
FROM dbo.t_al_host_order_master WITH (NOLOCK)
WHERE import_status='I' AND record_create_date < DATEADD(minute,-15,GETDATE());
"""


def main() -> int:
    real = wms_connect.run_query(REAL_ERRORS_SQL)
    stuck = int(wms_connect.run_query(STUCK_SQL).iloc[0]["stuck_in_progress"])

    lines = []
    if not real.empty:
        for _, r in real.iterrows():
            lines.append(
                f"{int(r['cnt'])}x  {r['real_error'].strip()}  "
                f"(e.g. order {r['an_order']} @ {r['a_wh']}, last {r['last_seen']})"
            )
    if stuck > 0:
        lines.append(f"{stuck} import(s) stuck in-progress ('I') > 15 min")

    if lines:
        mc.slack_alert(MONITOR, f"WMS import errors — last {WINDOW_MIN} min", lines)
        return 1

    mc.heartbeat(MONITOR, f"0 real errors, 0 stuck (last {WINDOW_MIN} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
