-- name: search
SELECT TOP 300 o.name, o.type_desc, o.create_date, o.modify_date, LEN(m.definition) AS def_len
FROM sys.objects o
LEFT JOIN sys.sql_modules m ON m.object_id = o.object_id
WHERE o.type IN ('P', 'V', 'FN', 'IF', 'TF', 'TR')
  AND (o.name LIKE :like OR (:body = 1 AND m.definition LIKE :like))
ORDER BY o.modify_date DESC

-- name: definition
SELECT o.name, o.type_desc, o.create_date, o.modify_date,
       OBJECT_DEFINITION(o.object_id) AS definition
FROM sys.objects o
WHERE o.object_id = OBJECT_ID(:name)

-- name: deps
SELECT DISTINCT 'uses' AS direction,
       COALESCE(d.referenced_schema_name, 'dbo') + '.' + d.referenced_entity_name AS object_name,
       o2.type_desc
FROM sys.sql_expression_dependencies d
LEFT JOIN sys.objects o2 ON o2.object_id = d.referenced_id
WHERE d.referencing_id = OBJECT_ID(:name)
UNION
SELECT DISTINCT 'used by',
       OBJECT_SCHEMA_NAME(d.referencing_id) + '.' + OBJECT_NAME(d.referencing_id),
       o1.type_desc
FROM sys.sql_expression_dependencies d
JOIN sys.objects o1 ON o1.object_id = d.referencing_id
WHERE d.referenced_id = OBJECT_ID(:name)
ORDER BY 1, 3, 2

-- name: parameters
SELECT p.parameter_id AS ord, p.name, TYPE_NAME(p.user_type_id) AS data_type,
       CASE WHEN TYPE_NAME(p.user_type_id) IN ('nvarchar','nchar') AND p.max_length > 0 THEN p.max_length / 2
            ELSE p.max_length END AS length,
       p.is_output, p.has_default_value
FROM sys.parameters p
WHERE p.object_id = OBJECT_ID(:name)
ORDER BY p.parameter_id

-- name: recent
SELECT TOP 100 o.name, o.type_desc, o.modify_date, o.create_date,
       CASE WHEN o.create_date = o.modify_date THEN 'new' ELSE 'modified' END AS change
FROM sys.objects o
WHERE o.type IN ('P', 'V', 'FN', 'IF', 'TF', 'TR', 'U')
  AND o.modify_date >= DATEADD(day, -:days, GETDATE())
ORDER BY o.modify_date DESC

-- name: proc_stats
SELECT TOP 50 OBJECT_NAME(ps.object_id) AS proc_name, ps.execution_count,
       ps.total_elapsed_time / 1000 AS total_elapsed_ms,
       ps.total_elapsed_time / NULLIF(ps.execution_count, 0) / 1000 AS avg_elapsed_ms,
       ps.total_worker_time / NULLIF(ps.execution_count, 0) / 1000 AS avg_cpu_ms,
       ps.total_logical_reads / NULLIF(ps.execution_count, 0) AS avg_logical_reads,
       ps.last_execution_time, ps.cached_time
FROM sys.dm_exec_procedure_stats ps
WHERE ps.database_id = DB_ID() AND OBJECT_NAME(ps.object_id) LIKE :like
ORDER BY ps.total_elapsed_time DESC

-- name: hash_list
SELECT o.name, o.type_desc, o.modify_date,
       CONVERT(varchar(64), HASHBYTES('SHA2_256', CAST(m.definition AS nvarchar(max))), 2) AS def_hash,
       LEN(m.definition) AS def_len
FROM sys.objects o
JOIN sys.sql_modules m ON m.object_id = o.object_id
WHERE o.type IN ('P', 'V', 'FN', 'IF', 'TF', 'TR') AND o.name LIKE :like
ORDER BY o.name
