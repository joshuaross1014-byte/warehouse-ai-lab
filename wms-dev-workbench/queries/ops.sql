-- Operational panels. Parameters: :days, :hours, :wh ('' = all).

-- name: orders_by_status
SELECT wh_id, status, COUNT(*) AS orders, MIN(order_date) AS oldest, MAX(order_date) AS newest
FROM t_order WITH (NOLOCK)
WHERE order_date >= DATEADD(day, -:days, GETDATE()) AND (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, status
ORDER BY wh_id, status

-- name: waves_by_status
SELECT wh_id, status, COUNT(*) AS waves, MIN(created_date) AS oldest_created,
       MAX(released_date) AS last_released
FROM t_wave_master WITH (NOLOCK)
WHERE created_date >= DATEADD(day, -:days, GETDATE()) AND (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, status
ORDER BY wh_id, status

-- name: wave_errors
SELECT TOP 100 log_date, wh_id, wave_id, obj_name, LEFT(log_message, 250) AS log_message
FROM t_log_wave_error WITH (NOLOCK)
WHERE log_date >= DATEADD(hour, -:hours, GETDATE()) AND (:wh = '' OR wh_id = :wh)
ORDER BY log_date DESC

-- name: import_errors
-- Benign wave/picking lock rejections are filtered with a broad LIKE here;
-- see claude-ops-toolkit/claude-skills/wms-import-errors for the exact patterns.
SELECT TOP 200 record_create_date, wh_id, order_number, order_type, processing_code,
       LEFT(error_msg, 250) AS error_msg
FROM t_al_host_order_master WITH (NOLOCK)
WHERE import_status = 'E'
  AND record_create_date >= DATEADD(hour, -:hours, GETDATE())
  AND (:wh = '' OR wh_id = :wh)
  AND error_msg NOT LIKE '%lock%'
ORDER BY record_create_date DESC

-- name: import_queue
SELECT wh_id, import_status, processing_code, COUNT(*) AS records,
       MIN(record_create_date) AS oldest, MAX(record_create_date) AS newest
FROM t_al_host_order_master WITH (NOLOCK)
WHERE record_create_date >= DATEADD(hour, -:hours, GETDATE()) AND (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, import_status, processing_code
ORDER BY wh_id, import_status

-- name: rf_sessions
SELECT e.wh_id, e.id, e.name, e.device, e.status, e.current_location, e.last_process,
       e.last_menu_item, e.last_tran_start_datetime, e.last_tran_end_datetime, e.work_q_id, e.zone
FROM t_employee e WITH (NOLOCK)
WHERE e.last_tran_start_datetime >= DATEADD(hour, -:hours, GETDATE()) AND (:wh = '' OR e.wh_id = :wh)
ORDER BY e.last_tran_start_datetime DESC

-- name: open_logons
SELECT TOP 200 wh_id, employee_id, tran_type, description, logon_start_date, logon_start_time,
       device, location_id, control_number
FROM t_employee_logon WITH (NOLOCK)
WHERE logon_end_date IS NULL AND (:wh = '' OR wh_id = :wh)
ORDER BY logon_start_date DESC, logon_start_time DESC

-- name: picks_by_status
SELECT wh_id, status, work_type, COUNT(*) AS picks, SUM(planned_quantity) AS planned,
       SUM(picked_quantity) AS picked, SUM(staged_quantity) AS staged, SUM(shipped_quantity) AS shipped
FROM t_pick_detail WITH (NOLOCK)
WHERE create_date >= DATEADD(day, -:days, GETDATE()) AND (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, status, work_type
ORDER BY wh_id, status, work_type

-- name: tran_activity_today
SELECT wh_id, tran_type, description, COUNT(*) AS trans, COUNT(DISTINCT employee_id) AS operators,
       SUM(tran_qty) AS qty
FROM t_tran_log WITH (NOLOCK)
WHERE start_tran_date >= CAST(GETDATE() AS date) AND (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, tran_type, description
ORDER BY wh_id, trans DESC

-- name: blocking
SELECT r.session_id, r.blocking_session_id, r.status, r.command, r.wait_type, r.wait_time,
       r.cpu_time, r.total_elapsed_time, s.login_name, s.host_name, s.program_name,
       DB_NAME(r.database_id) AS db, SUBSTRING(t.text, 1, 300) AS sql_text
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id <> @@SPID AND s.is_user_process = 1
ORDER BY r.blocking_session_id DESC, r.total_elapsed_time DESC

-- name: whse_control
SELECT wh_id, control_type, description, next_value, config_display, allow_edit, c1, c2, f1
FROM t_whse_control WITH (NOLOCK)
WHERE (:wh = '' OR wh_id = :wh)
ORDER BY wh_id, control_type

-- name: location_status
SELECT wh_id, zone, status, type, COUNT(*) AS locations, SUM(stored_qty) AS stored_qty
FROM t_location WITH (NOLOCK)
WHERE (:wh = '' OR wh_id = :wh)
GROUP BY wh_id, zone, status, type
ORDER BY wh_id, zone, status

-- name: warehouses
SELECT wh_id, COUNT(*) AS items
FROM t_item_master WITH (NOLOCK)
GROUP BY wh_id
ORDER BY wh_id
