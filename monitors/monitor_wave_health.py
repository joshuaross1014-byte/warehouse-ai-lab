"""Monitor: WMS wave & staged-inventory health.

Alerts on: (1) allocating waves stuck > 2h (hung allocation), and
(2) serial-completeness mismatches — serial-managed pallets where the captured
serial count <> on-hand qty (strands inventory and blocks the ERP receipt/delivery).
Silent when clean. Intended to run hourly (ops hours) under Task Scheduler.
"""
import monitor_common as mc
import wms_connect

MONITOR = "wave_health"

# Wave status codes are product-standard: N=new, H=hold, A=allocating,
# R=released. A stuck 'A' wave is the sharp signal (allocation hung); aged N/H
# waves are mostly a historical backlog, so they are intentionally not alerted.
STUCK_A_SQL = """
SELECT wh_id, wave_id, DATEDIFF(hour,created_date,GETDATE()) AS age_h
FROM dbo.t_wave_master WITH (NOLOCK)
WHERE status='A' AND released_date IS NULL AND created_date < DATEADD(hour,-2,GETDATE())
ORDER BY age_h DESC;
"""

# serial_control='F' = serial-managed item. Count captured serials per stored
# unit and flag any where that count != on-hand qty.
SERIAL_MISMATCH_SQL = """
SELECT si.wh_id, si.item_number, si.hu_id AS lpn, si.actual_qty,
       COUNT(sn.serial_number_id) AS serial_cnt, si.shipment_number
FROM dbo.t_stored_item si WITH (NOLOCK)
JOIN dbo.t_item_master im WITH (NOLOCK)
     ON im.item_number=si.item_number AND im.wh_id=si.wh_id AND im.serial_control='F'
LEFT JOIN dbo.t_serial_number sn WITH (NOLOCK) ON sn.sto_id=si.sto_id
WHERE si.actual_qty > 0
GROUP BY si.wh_id, si.item_number, si.hu_id, si.actual_qty, si.shipment_number
HAVING COUNT(sn.serial_number_id) <> si.actual_qty
ORDER BY si.wh_id;
"""


def main() -> int:
    stuck = wms_connect.run_query(STUCK_A_SQL)
    serial = wms_connect.run_query(SERIAL_MISMATCH_SQL)

    lines = []
    for _, r in stuck.iterrows():
        lines.append(f"STUCK allocating wave {r['wave_id']} @ {r['wh_id']} — {int(r['age_h'])}h")
    for _, r in serial.iterrows():
        lines.append(
            f"SERIAL mismatch @ {r['wh_id']}: item {r['item_number']} LPN {r['lpn']} — "
            f"qty {r['actual_qty']} vs {int(r['serial_cnt'])} serials"
            + (f" (shpmt {r['shipment_number']})" if r['shipment_number'] else "")
        )

    if lines:
        mc.slack_alert(MONITOR, "WMS wave health", lines)
        return 1

    mc.heartbeat(MONITOR, "0 stuck 'A' waves, 0 serial mismatches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
