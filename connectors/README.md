# connectors

Thin, env-driven connection helpers shared by the monitors (and usable from any
script or notebook). No endpoints or credentials live in code — copy
`.env.example` to `.env` and fill it in. `.env` is git-ignored.

| Module | Target | Returns |
|---|---|---|
| `wms_connect.py` | WMS (SQL Server) | `get_engine()`, `run_query(sql) -> DataFrame` |
| `hana_connect.py` | ERP / SAP B1 (HANA) | `get_connection()` (hdbcli, read-only) |
| `robo_connect.py` | RPA control room REST | `get_session() -> (session, base_url)` |

Requires: `sqlalchemy`, `pyodbc`, `pandas` (WMS); `hdbcli` (HANA); `requests`
(RPA); `python-dotenv` (all, optional but recommended).
