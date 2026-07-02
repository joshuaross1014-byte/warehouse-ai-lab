"""Live-mode extractor: dump every module definition from a SQL Server
database to .sql files, ready for `python -m sqlcodebase index`.

Connection comes from environment variables (nothing in code):
    SQLCB_SERVER, SQLCB_DB, SQLCB_USER, SQLCB_PASS
    SQLCB_DRIVER (optional, default "ODBC Driver 18 for SQL Server")

Usage:
    python scripts/extract_mssql.py <out_dir>

Reads sys.sql_modules (procedures, views, functions, triggers) and scripts
CREATE TABLE stubs from INFORMATION_SCHEMA.COLUMNS so tables are defined
nodes, not inferred. Read-only.
"""
import os
import re
import sys
from pathlib import Path

import pyodbc


def main(out_dir: str) -> None:
    server, db = os.environ["SQLCB_SERVER"], os.environ["SQLCB_DB"]
    user, pwd = os.environ["SQLCB_USER"], os.environ["SQLCB_PASS"]
    driver = os.getenv("SQLCB_DRIVER", "ODBC Driver 18 for SQL Server")
    cn = pyodbc.connect(f"Driver={{{driver}}};Server={server};Database={db};"
                        f"UID={user};PWD={pwd};TrustServerCertificate=yes;Encrypt=yes;")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cur = cn.cursor()
    cur.execute("""
        SELECT s.name, o.name, o.type_desc, m.definition
        FROM sys.sql_modules m WITH (NOLOCK)
        JOIN sys.objects o WITH (NOLOCK) ON o.object_id = m.object_id
        JOIN sys.schemas s WITH (NOLOCK) ON s.schema_id = o.schema_id
        WHERE o.is_ms_shipped = 0""")
    n_mod = 0
    for schema, name, tdesc, definition in cur.fetchall():
        safe = re.sub(r"[^\w.-]", "_", f"{schema}.{name}")
        (out / f"{safe}.sql").write_text(definition or "", encoding="utf-8")
        n_mod += 1

    cur.execute("""
        SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WITH (NOLOCK)
        WHERE TABLE_TYPE = 'BASE TABLE'""")
    tables = cur.fetchall()
    stub = "\n".join(f"CREATE TABLE {s}.{t} (placeholder int);" for s, t in tables)
    (out / "_tables.sql").write_text(stub, encoding="utf-8")

    print(f"extracted {n_mod} modules + {len(tables)} table stubs -> {out}")
    cn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "extracted_sql")
