"""WMS (SQL Server) connection helper — env-driven, read-oriented.

All connection details come from environment variables (or a local .env loaded
by python-dotenv). Nothing site-specific is hard-coded.

Required env:
    WMS_DB_HOST     SQL Server host or IP
    WMS_DB_NAME     database name
    WMS_DB_USER     SQL login
    WMS_DB_PASS     password
Optional:
    WMS_DB_DRIVER   ODBC driver name (default "ODBC Driver 18 for SQL Server")
"""
from __future__ import annotations

import os
import urllib.parse

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                override=False)
except ImportError:
    pass

DRIVER = os.getenv("WMS_DB_DRIVER", "ODBC Driver 18 for SQL Server")


def get_engine() -> Engine:
    """Return a SQLAlchemy engine for the WMS database."""
    host = os.environ["WMS_DB_HOST"]
    db = os.environ["WMS_DB_NAME"]
    user = os.environ["WMS_DB_USER"]
    pwd = os.environ["WMS_DB_PASS"]
    odbc = (
        f"Driver={{{DRIVER}}};Server={host};Database={db};"
        f"UID={user};PWD={pwd};TrustServerCertificate=yes;Encrypt=yes;"
    )
    url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc)
    return create_engine(url, fast_executemany=True)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a read-only query and return a DataFrame.

    Use :name placeholders + a params dict. Add WITH (NOLOCK) on table reads to
    avoid blocking production writers.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


if __name__ == "__main__":
    print(run_query("SELECT TOP 5 name FROM sys.tables WITH (NOLOCK) ORDER BY name")
          .to_string(index=False))
