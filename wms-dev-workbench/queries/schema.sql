-- name: tables
SELECT s.name AS schema_name, t.name AS table_name, SUM(p.rows) AS row_count,
       t.create_date, t.modify_date
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE t.name LIKE :like
GROUP BY s.name, t.name, t.create_date, t.modify_date
ORDER BY t.name

-- name: views
SELECT s.name AS schema_name, v.name AS view_name, v.create_date, v.modify_date
FROM sys.views v JOIN sys.schemas s ON s.schema_id = v.schema_id
WHERE v.name LIKE :like
ORDER BY v.name

-- name: columns
SELECT c.column_id AS ord, c.name AS column_name, TYPE_NAME(c.user_type_id) AS data_type,
       CASE WHEN TYPE_NAME(c.user_type_id) IN ('nvarchar','nchar') AND c.max_length > 0 THEN c.max_length / 2
            ELSE c.max_length END AS length,
       c.precision, c.scale, c.is_nullable, c.is_identity, c.is_computed,
       d.definition AS default_value,
       CASE WHEN EXISTS (SELECT 1 FROM sys.index_columns ic
                         JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                         WHERE i.is_primary_key = 1 AND ic.object_id = c.object_id AND ic.column_id = c.column_id)
            THEN 1 ELSE 0 END AS is_pk
FROM sys.columns c
LEFT JOIN sys.default_constraints d ON d.object_id = c.default_object_id
WHERE c.object_id = OBJECT_ID(:table)
ORDER BY c.column_id

-- name: indexes
SELECT i.name AS index_name, i.type_desc, i.is_unique, i.is_primary_key, i.filter_definition,
       STUFF((SELECT ', ' + COL_NAME(ic.object_id, ic.column_id)
              FROM sys.index_columns ic
              WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
              ORDER BY ic.key_ordinal FOR XML PATH('')), 1, 2, '') AS key_columns,
       STUFF((SELECT ', ' + COL_NAME(ic.object_id, ic.column_id)
              FROM sys.index_columns ic
              WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 1
              FOR XML PATH('')), 1, 2, '') AS included_columns,
       us.user_seeks, us.user_scans, us.user_lookups, us.user_updates, us.last_user_seek
FROM sys.indexes i
LEFT JOIN sys.dm_db_index_usage_stats us
       ON us.object_id = i.object_id AND us.index_id = i.index_id AND us.database_id = DB_ID()
WHERE i.object_id = OBJECT_ID(:table) AND i.index_id > 0
ORDER BY i.is_primary_key DESC, i.name

-- name: foreign_keys
SELECT fk.name AS fk_name,
       OBJECT_NAME(fk.parent_object_id) AS from_table,
       COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS from_column,
       OBJECT_NAME(fk.referenced_object_id) AS to_table,
       COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS to_column,
       fk.is_disabled
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
WHERE fk.parent_object_id = OBJECT_ID(:table) OR fk.referenced_object_id = OBJECT_ID(:table)
ORDER BY from_table, fk.name

-- name: triggers
SELECT tr.name AS trigger_name, tr.is_disabled, tr.is_instead_of_trigger, tr.modify_date,
       STUFF((SELECT ', ' + te.type_desc FROM sys.trigger_events te WHERE te.object_id = tr.object_id FOR XML PATH('')), 1, 2, '') AS events
FROM sys.triggers tr
WHERE tr.parent_id = OBJECT_ID(:table)
ORDER BY tr.name

-- name: find_column
SELECT TOP 500 OBJECT_NAME(c.object_id) AS table_name, c.name AS column_name,
       TYPE_NAME(c.user_type_id) AS data_type,
       CASE WHEN TYPE_NAME(c.user_type_id) IN ('nvarchar','nchar') AND c.max_length > 0 THEN c.max_length / 2
            ELSE c.max_length END AS length,
       c.is_nullable, o.type_desc AS object_type
FROM sys.columns c JOIN sys.objects o ON o.object_id = c.object_id
WHERE c.name LIKE :like AND o.type IN ('U', 'V')
ORDER BY c.name, table_name

-- name: used_by
SELECT DISTINCT OBJECT_SCHEMA_NAME(d.referencing_id) + '.' + OBJECT_NAME(d.referencing_id) AS object_name,
       o.type_desc, o.modify_date
FROM sys.sql_expression_dependencies d
JOIN sys.objects o ON o.object_id = d.referencing_id
WHERE d.referenced_id = OBJECT_ID(:name)
ORDER BY o.type_desc, object_name
