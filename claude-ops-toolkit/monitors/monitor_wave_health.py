"""Monitor: WMS wave & staged-inventory health.

Alerts on: (1) allocating waves stuck > 2h (hung allocation), and
(2) serial-completeness mismatches — serial-managed pallets where the captured
serial count <> on-hand qty (strands inventory and blocks the ERP receipt/delivery), and
(3) stranded work-queue batches — a crashed RF session never returned its worker
slot, so the batch's remaining lines are invisible on every scanner (alert-only).
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

# Stranded batches: dispatch only offers a batch while workers_assigned <
# workers_required, so a session that crashed without returning its slot hides
# the batch's RELEASED+allocated lines from everyone. Also catches batches
# created with workers_required = 0, which can never dispatch (0 < 0).
# ALERT-ONLY by design: an idle-but-live batch (a long break) must not be
# auto-released, or two pickers get sent to the same bins. Quiet filter = no
# pick/stage transaction on the batch's orders for 3h+.
STRANDED_BATCH_SQL = """
SELECT wq.wh_id, wq.work_q_id, wq.work_status,
       wq.workers_assigned, wq.workers_required,
       COUNT(DISTINCT pd.pick_id) AS stuck_lines
FROM dbo.t_work_q wq WITH (NOLOCK)
JOIN dbo.t_pick_detail pd WITH (NOLOCK) ON pd.work_q_id = wq.work_q_id AND pd.status = 'RELEASED'
JOIN dbo.t_allocation a WITH (NOLOCK) ON a.pick_id = pd.pick_id
WHERE wq.work_status IN ('A','U')
  AND wq.workers_assigned >= wq.workers_required
  AND NOT EXISTS (SELECT 1 FROM dbo.t_tran_log tl WITH (NOLOCK)
                  JOIN dbo.t_pick_detail p2 WITH (NOLOCK)
                       ON p2.work_q_id = wq.work_q_id AND p2.order_number = tl.outbound_order_number
                  WHERE tl.wh_id = wq.wh_id AND tl.tran_type IN ('301','302')
                    AND tl.start_tran_date >= CONVERT(date, GETDATE())
                    AND tl.start_tran_time >= DATEADD(hour, -3, CAST(CAST(GETDATE() AS time) AS datetime)))
GROUP BY wq.wh_id, wq.work_q_id, wq.work_status, wq.workers_assigned, wq.workers_required
ORDER BY wq.wh_id, wq.work_q_id;
"""


def main() -> int:
    stuck = wms_connect.run_query(STUCK_A_SQL)
    serial = wms_connect.run_query(SERIAL_MISMATCH_SQL)
    stranded = wms_connect.run_query(STRANDED_BATCH_SQL)

    lines = []
    for _, r in stuck.iterrows():
        lines.append(f"STUCK allocating wave {r['wave_id']} @ {r['wh_id']} — {int(r['age_h'])}h")
    for _, r in serial.iterrows():
        lines.append(
            f"SERIAL mismatch @ {r['wh_id']}: item {r['item_number']} LPN {r['lpn']} — "
            f"qty {r['actual_qty']} vs {int(r['serial_cnt'])} serials"
            + (f" (shpmt {r['shipment_number']})" if r['shipment_number'] else "")
        )
    for _, r in stranded.iterrows():
        lines.append(
            f"STRANDED batch {r['work_q_id']} @ {r['wh_id']} — {int(r['stuck_lines'])} lines invisible "
            f"(workers {int(r['workers_assigned'])}/{int(r['workers_required'])}, quiet 3h+). "
            f"Confirm nobody is on it, then release: UPDATE t_work_q SET work_status='U', "
            f"workers_assigned=workers_assigned-1 WHERE work_q_id='{r['work_q_id']}'"
        )

    if lines:
        mc.slack_alert(MONITOR, "WMS wave health", lines)
        return 1

    mc.heartbeat(MONITOR, "0 stuck 'A' waves, 0 serial mismatches, 0 stranded batches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
