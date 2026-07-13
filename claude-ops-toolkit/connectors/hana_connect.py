"""ERP (SAP Business One on SAP HANA) connection helper — env-driven, READ-ONLY.

Uses the SAP HANA Python client (hdbcli). All details come from environment
variables (or a local .env). Intended for a read-only DB login.

Required env:
    ERP_HANA_HOST     HANA host or IP
    ERP_HANA_PORT     SQL port (e.g. 30015 for single-container instance 00)
    ERP_HANA_USER     read-only login
    ERP_HANA_PASS     password
Optional:
    ERP_HANA_SCHEMA   default company schema to resolve unqualified names
"""
from __future__ import annotations

import os

from hdbcli import dbapi

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                override=False)
except ImportError:
    pass

COMM_TIMEOUT_MS = 60000


def get_connection():
    """Return a read-only hdbcli connection to the ERP HANA database."""
    conn = dbapi.connect(
        address=os.environ["ERP_HANA_HOST"],
        port=int(os.environ["ERP_HANA_PORT"]),
        user=os.environ["ERP_HANA_USER"],
        password=os.environ["ERP_HANA_PASS"],
        currentSchema=os.getenv("ERP_HANA_SCHEMA") or None,
        autocommit=True,
        connectTimeout=10000,
        communicationTimeout=COMM_TIMEOUT_MS,
    )
    return conn


if __name__ == "__main__":
    c = get_connection()
    cur = c.cursor()
    cur.execute("SELECT TOP 5 SCHEMA_NAME, TABLE_NAME FROM SYS.TABLES ORDER BY TABLE_NAME")
    for row in cur.fetchall():
        print(row[0], row[1])
    cur.close()
    c.close()
