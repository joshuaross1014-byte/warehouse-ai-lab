-- Demo corpus: a miniature order-management codebase so the tool is
-- runnable out of the box:  python -m sqlcodebase index demo/

CREATE TABLE orders (order_number varchar(30), wh_id varchar(10), status char(1));
CREATE TABLE order_detail (order_number varchar(30), line_no int, item varchar(30), qty int);
CREATE TABLE inventory (item varchar(30), wh_id varchar(10), on_hand int, allocated int);
CREATE TABLE audit_log (event_time datetime, source varchar(50), message varchar(500));
CREATE TABLE host_order_queue (id int, order_number varchar(30), import_status char(1), error_msg varchar(500));

CREATE VIEW v_open_orders AS
SELECT o.order_number, o.wh_id, d.item, d.qty
FROM orders o JOIN order_detail d ON d.order_number = o.order_number
WHERE o.status = 'N';

CREATE PROCEDURE usp_log_event @source varchar(50), @msg varchar(500) AS
BEGIN
  INSERT INTO audit_log (event_time, source, message) VALUES (GETDATE(), @source, @msg);
END;

CREATE PROCEDURE usp_import_order @order varchar(30) AS
BEGIN
  -- pull from the host staging queue into the live tables
  INSERT INTO orders (order_number, wh_id, status)
  SELECT order_number, 'DC1', 'N' FROM host_order_queue WHERE order_number = @order;
  UPDATE host_order_queue SET import_status = 'S' WHERE order_number = @order;
  EXEC usp_log_event 'import', @order;
END;

CREATE PROCEDURE usp_allocate_order @order varchar(30) AS
BEGIN
  UPDATE inventory SET allocated = allocated + d.qty
  FROM inventory i JOIN order_detail d ON d.item = i.item
  WHERE d.order_number = @order;
  UPDATE orders SET status = 'A' WHERE order_number = @order;
  EXEC usp_log_event 'allocate', @order;
END;

CREATE PROCEDURE usp_ship_order @order varchar(30) AS
BEGIN
  EXEC usp_allocate_order @order;
  UPDATE inventory SET on_hand = on_hand - allocated, allocated = 0
  FROM inventory i JOIN order_detail d ON d.item = i.item
  WHERE d.order_number = @order;
  UPDATE orders SET status = 'D' WHERE order_number = @order;
  EXEC usp_log_event 'ship', @order;
END;

CREATE TRIGGER trg_orders_audit ON orders AFTER UPDATE AS
BEGIN
  INSERT INTO audit_log (event_time, source, message)
  SELECT GETDATE(), 'trg_orders_audit', order_number FROM inserted;
END;
