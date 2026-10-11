"""
config.py - environment-driven settings for the WMS Dev Workbench.

Everything that differs between machines or people lives here and is read from
environment variables (or a local .env next to this file). No credentials are
written in code; the same rule as wms_connect.py / the MCP servers.

Profiles
    PROD  -> prod-sql.example.local   read-only, always (the guard cannot be switched off)
    TEST  -> test-sql.example.local   read-only unless WORKBENCH_ALLOW_WRITES=1

Env vars
    WMS_USER / WMS_PASS              PROD SQL login 
    WMS_TEST_USER / WMS_TEST_PASS    TEST SQL login (falls back to WMS_USER / WMS_PASS)
    WORKBENCH_PROD_SERVER / WORKBENCH_TEST_SERVER / WORKBENCH_DATABASE   overrides
    WORKBENCH_ALLOW_WRITES=1         enables DML on TEST only
    WORKBENCH_PORT                   default 8765
    WORKBENCH_MAX_ROWS               default 500 (hard cap 5000)
    WORKBENCH_QUERY_TIMEOUT          seconds, default 30
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE, # comments). Real env vars win over the file."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(HERE / ".env")


@dataclass(frozen=True)
class Profile:
    name: str
    server: str
    database: str
    user_env: str
    pass_env: str
    fallback_user_env: str | None
    fallback_pass_env: str | None
    writable: bool          # whether the write guard MAY be bypassed on this profile
    color: str              # UI accent so PROD is unmistakable

    def credentials(self) -> tuple[str, str]:
        user = os.getenv(self.user_env) or (os.getenv(self.fallback_user_env) if self.fallback_user_env else None)
        pwd = os.getenv(self.pass_env) or (os.getenv(self.fallback_pass_env) if self.fallback_pass_env else None)
        if not user or not pwd:
            raise RuntimeError(
                f"Missing credentials for profile {self.name}: set {self.user_env} and {self.pass_env}"
            )
        return user, pwd


DATABASE = os.getenv("WORKBENCH_DATABASE", "WMS")
DRIVER = os.getenv("WORKBENCH_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

PROFILES: dict[str, Profile] = {
    "PROD": Profile(
        name="PROD",
        server=os.getenv("WORKBENCH_PROD_SERVER", "prod-sql.example.local"),
        database=DATABASE,
        user_env="WMS_USER",
        pass_env="WMS_PASS",
        fallback_user_env=None,
        fallback_pass_env=None,
        writable=False,
        color="#e5484d",
    ),
    "TEST": Profile(
        name="TEST",
        server=os.getenv("WORKBENCH_TEST_SERVER", "test-sql.example.local"),
        database=DATABASE,
        user_env="WMS_TEST_USER",
        pass_env="WMS_TEST_PASS",
        fallback_user_env="WMS_USER",
        fallback_pass_env="WMS_PASS",
        writable=os.getenv("WORKBENCH_ALLOW_WRITES") == "1",
        color="#30a46c",
    ),
}

DEFAULT_PROFILE = os.getenv("WORKBENCH_DEFAULT_PROFILE", "PROD")
PORT = int(os.getenv("WORKBENCH_PORT", "8765"))
MAX_ROWS_DEFAULT = int(os.getenv("WORKBENCH_MAX_ROWS", "500"))
MAX_ROWS_HARD_CAP = 5000
QUERY_TIMEOUT = int(os.getenv("WORKBENCH_QUERY_TIMEOUT", "30"))
STATE_DB = HERE / "workbench.sqlite"      # query history + saved queries (local, per machine)
QUERIES_DIR = HERE / "queries"


def get_profile(name: str | None) -> Profile:
    key = (name or DEFAULT_PROFILE).upper()
    if key not in PROFILES:
        raise KeyError(f"Unknown profile '{name}'. Choose one of {list(PROFILES)}")
    return PROFILES[key]
