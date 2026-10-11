-- Every block takes :n (the key) and most take :wh ('' = all warehouses).
-- WITH (NOLOCK) on dbo.* reads is the house rule on the production box.

-- name: order_header
SELECT TOP 5 order_id, wh_id, order_number, display_order_number, type_id, status,
       customer_name, ship_to_code, ship_to_name, order_date, date_expected,
       earliest_ship_date, latest_ship_date, actual_ship_date, date_picked,
       load_id, bol_number, carrier, priority, rush, zone, lock_flag,
       partial_order_flag, backorder, route, warehouse_owner
FROM t_order WITH (NOLOCK)
WHERE order_number = :n AND (:wh = '' OR wh_id = :wh)

-- name: order_lines
SELECT wh_id, line_number, item_number, item_description, qty, qty_shipped, bo_qty,
       order_uom, lot_number, picking_flow, host_wave_id, line_type, hold_reason_id,
       unit_weight, date_expected
FROM t_order_detail WITH (NOLOCK)
WHERE order_number = :n AND (:wh = '' OR wh_id = :wh)
ORDER BY line_number

-- name: order_picks
SELECT pick_id, wh_id, line_number, item_number, type, status, work_type, wave_id, zone, pick_area,
       planned_quantity, picked_quantity, staged_quantity, loaded_quantity, shipped_quantity,
       uom, lot_number, container_id, staging_location, user_assigned, picked_by,
       work_q_id, bulk_pick_flag, hold_reason_id, create_date, prev_pick_id
FROM t_pick_detail WITH (NOLOCK)
WHERE order_number = :n AND (:wh = '' OR wh_id = :wh)
ORDER BY pick_id

-- name: order_waves
SELECT DISTINCT w.wave_id, w.wh_id, w.status, w.staging_location, w.door_location,
       w.created_date, w.released_date, w.earliest_ship_date, w.latest_ship_date
FROM t_wave_master w WITH (NOLOCK)
JOIN t_pick_detail p WITH (NOLOCK) ON p.wave_id = w.wave_id AND p.wh_id = w.wh_id
WHERE p.order_number = :n AND (:wh = '' OR p.wh_id = :wh)

-- name: order_hus
SELECT h.hu_id, h.wh_id, h.type, h.subtype, h.status, h.location_id, h.control_number,
       h.load_id, h.load_seq, h.zone, h.parent_hu_id, h.user_id, h.fifo_date
FROM t_hu_master h WITH (NOLOCK)
WHERE h.hu_id IN (SELECT container_id FROM t_pick_detail WITH (NOLOCK)
                  WHERE order_number = :n AND container_id IS NOT NULL)
   OR h.control_number = :n
ORDER BY h.hu_id

-- name: order_host
SELECT TOP 20 host_order_master_id, record_create_date, wh_id, processing_code, import_status,
       LEFT(error_msg, 300) AS error_msg, order_type, customer_code, host_group_id
FROM t_al_host_order_master WITH (NOLOCK)
WHERE order_number = :n OR display_order_number = :n
ORDER BY record_create_date DESC

-- name: order_tranlog
SELECT TOP 300 tran_log_id, tran_type, description, start_tran_date, start_tran_time, end_tran_time,
       employee_id, item_number, tran_qty, uom, source_location_id, destination_location_id,
       source_hu_id, destination_hu_id, wave_id, pick_id, work_q_id, load_id, reason_code
FROM t_tran_log WITH (NOLOCK)
WHERE outbound_order_number = :n OR outbound_order_number2 = :n
ORDER BY tran_log_id DESC

-- name: item_master
SELECT item_master_id, wh_id, item_number, display_item_number, description, uom,
       lot_control, serial_control, expiration_date_control, manual_expiry, shelf_life,
       pick_location, pick_put_id, class_id, inv_cat, inv_class, catch_weight,
       item_category, item_department, vendor_code, upc, unit_weight, cross_dock, barcode_type
FROM t_item_master WITH (NOLOCK)
WHERE item_number = :n OR display_item_number = :n OR upc = :n
ORDER BY wh_id

-- name: item_uom
SELECT *
FROM t_item_uom WITH (NOLOCK)
WHERE item_number = :n AND (:wh = '' OR wh_id = :wh)

-- name: item_stock
SELECT wh_id, location_id, hu_id, lot_number, actual_qty, unavailable_qty, status, type,
       fifo_date, expiration_date, reserved_for, put_away_location, inspection_code
FROM t_stored_item WITH (NOLOCK)
WHERE item_number = :n AND (:wh = '' OR wh_id = :wh)
ORDER BY wh_id, location_id

-- name: item_picks
SELECT TOP 200 pick_id, wh_id, order_number, line_number, status, work_type, wave_id, zone,
       planned_quantity, picked_quantity, staged_quantity, shipped_quantity, uom,
       lot_number, container_id, user_assigned, create_date
FROM t_pick_detail WITH (NOLOCK)
WHERE item_number = :n AND (:wh = '' OR wh_id = :wh)
  AND create_date >= DATEADD(day, -14, GETDATE())
ORDER BY pick_id DESC

-- name: item_tranlog
SELECT TOP 200 tran_log_id, wh_id, tran_type, description, start_tran_date, start_tran_time,
       employee_id, tran_qty, uom, source_location_id, destination_location_id,
       source_hu_id, destination_hu_id, outbound_order_number, inbound_order_number, lot_number
FROM t_tran_log WITH (NOLOCK)
WHERE item_number = :n AND (:wh = '' OR wh_id = :wh)
  AND start_tran_date >= DATEADD(day, -7, CAST(GETDATE() AS date))
ORDER BY tran_log_id DESC

-- name: hu_master
SELECT hu_id, wh_id, type, subtype, status, location_id, control_number, load_id, load_seq,
       zone, reserved_for, container_type, parent_hu_id, user_id, fifo_date, ver_flag
FROM t_hu_master WITH (NOLOCK)
WHERE hu_id = :n OR parent_hu_id = :n

-- name: hu_contents
SELECT wh_id, location_id, item_number, lot_number, actual_qty, unavailable_qty, status, type,
       fifo_date, expiration_date, reserved_for, shipment_number
FROM t_stored_item WITH (NOLOCK)
WHERE hu_id = :n
ORDER BY item_number

-- name: hu_tranlog
SELECT TOP 200 tran_log_id, wh_id, tran_type, description, start_tran_date, start_tran_time,
       employee_id, item_number, tran_qty, uom, source_location_id, destination_location_id,
       source_hu_id, destination_hu_id, outbound_order_number, inbound_order_number, wave_id
FROM t_tran_log WITH (NOLOCK)
WHERE source_hu_id = :n OR destination_hu_id = :n
ORDER BY tran_log_id DESC

-- name: po_master
SELECT po_id, wh_id, po_number, display_po_number, type_id, vendor_code, status, create_date,
       closed_date, po_posting_date, appointment_number, scheduled_start, carrier_scac, warehouse_owner
FROM t_po_master WITH (NOLOCK)
WHERE po_number = :n OR display_po_number = :n

-- name: po_lines
SELECT *
FROM t_po_detail WITH (NOLOCK)
WHERE po_number = :n AND (:wh = '' OR wh_id = :wh)

-- name: po_receipts
SELECT receipt_identity, receipt_id, wh_id, line_number, item_number, lot_number, qty_received,
       qty_damaged, receipt_uom, hu_id, status, tran_status, receipt_date, fork_id, shipment_number, hold_reason_id
FROM t_receipt WITH (NOLOCK)
WHERE po_number = :n AND (:wh = '' OR wh_id = :wh)
ORDER BY receipt_identity DESC

-- name: po_tranlog
SELECT TOP 200 tran_log_id, wh_id, tran_type, description, start_tran_date, start_tran_time,
       employee_id, item_number, tran_qty, uom, destination_location_id, destination_hu_id,
       receipt_id, expiration_date, lot_number
FROM t_tran_log WITH (NOLOCK)
WHERE inbound_order_number = :n
ORDER BY tran_log_id DESC

-- name: wave_master
SELECT wave_id, wh_id, status, sequence, staging_location, door_location,
       created_date, released_date, earliest_ship_date, latest_ship_date
FROM t_wave_master WITH (NOLOCK)
WHERE wave_id = :n

-- name: wave_orders
SELECT order_number, status, work_type, COUNT(*) AS picks,
       SUM(planned_quantity) AS planned, SUM(picked_quantity) AS picked,
       SUM(staged_quantity) AS staged, SUM(loaded_quantity) AS loaded, SUM(shipped_quantity) AS shipped,
       COUNT(DISTINCT user_assigned) AS assigned_users
FROM t_pick_detail WITH (NOLOCK)
WHERE wave_id = :n
GROUP BY order_number, status, work_type
ORDER BY order_number, status

-- name: wave_error_log
SELECT seq_id, log_date, wh_id, obj_name, LEFT(log_message, 400) AS log_message, user_log_message
FROM t_log_wave_error WITH (NOLOCK)
WHERE wave_id = :n
ORDER BY seq_id DESC

-- name: wave_autorelease
SELECT *
FROM t_autorelease_log WITH (NOLOCK)
WHERE wave_id = :n

-- name: emp_master
SELECT id, name, wh_id, status, dept, menu_level, device, device_type, current_location,
       work_q_id, zone, pick_area, work_shift, language_code, business_process, last_process,
       last_menu_item, last_tran_start_datetime, last_tran_end_datetime, last_loc_id, hu_id
FROM t_employee WITH (NOLOCK)
WHERE id = :n OR name = :n

-- name: emp_logons
SELECT TOP 50 wh_id, tran_type, description, logon_start_date, logon_start_time,
       logon_end_date, logon_end_time, logon_time, device, location_id, control_number
FROM t_employee_logon WITH (NOLOCK)
WHERE employee_id = :n
ORDER BY logon_start_date DESC, logon_start_time DESC

-- name: emp_tranlog
SELECT TOP 200 tran_log_id, wh_id, tran_type, description, start_tran_date, start_tran_time,
       end_tran_time, elapsed_time, item_number, tran_qty, uom, source_location_id,
       destination_location_id, outbound_order_number, inbound_order_number, wave_id, pick_id
FROM t_tran_log WITH (NOLOCK)
WHERE employee_id = :n
ORDER BY tran_log_id DESC

-- name: loc_master
SELECT wh_id, location_id, description, status, type, zone, picking_flow, pick_area,
       capacity_qty, stored_qty, capacity_uom, allow_bulk_pick, replenishment_location_id,
       aisle, bay, lev, slot, fifo_date, last_count_date, cycle_count_class, act_zone, pick_type
FROM t_location WITH (NOLOCK)
WHERE location_id = :n AND (:wh = '' OR wh_id = :wh)

-- name: loc_stock
SELECT wh_id, item_number, hu_id, lot_number, actual_qty, unavailable_qty, status, type,
       fifo_date, expiration_date, reserved_for
FROM t_stored_item WITH (NOLOCK)
WHERE location_id = :n AND (:wh = '' OR wh_id = :wh)
ORDER BY item_number

-- name: loc_tranlog
SELECT TOP 200 tran_log_id, wh_id, tran_type, description, start_tran_date, start_tran_time,
       employee_id, item_number, tran_qty, uom, source_location_id, destination_location_id,
       source_hu_id, destination_hu_id, outbound_order_number, inbound_order_number
FROM t_tran_log WITH (NOLOCK)
WHERE (source_location_id = :n OR destination_location_id = :n) AND (:wh = '' OR wh_id = :wh)
  AND start_tran_date >= DATEADD(day, -7, CAST(GETDATE() AS date))
ORDER BY tran_log_id DESC
