r"""
config.py - settings for the standalone WMS agent.

Everything that differs between machines comes from environment variables or a
local .env next to this file. No credential is ever written in code.

Required
    ANTHROPIC_API_KEY        Claude API key
    WMS_USER / WMS_PASS      SQL login (a READ-ONLY login is recommended for shared use)
    WMS_PROD_SERVER          production SQL host (or set WMS_AGENT_SERVERS, see below)

Optional
    WMS_TEST_SERVER          test SQL host
    WMS_DATABASE             database name (default WMS)
    WMS_AGENT_SERVERS        JSON overriding the registry, e.g.
                             {"prod": {"host": "...", "db": "WMS", "production": true, "cred_prefix": "WMS"},
                              "test": {"host": "...", "db": "WMS", "production": false, "cred_prefix": "WMS"}}
    WMS_AGENT_MODEL          default claude-opus-5-5
    WMS_AGENT_EFFORT         low | medium | high | xhigh | max   (default high)
    WMS_AGENT_MAX_ROWS       rows returned per SQL call (default 200, hard cap 1000)
    WMS_AGENT_QUERY_TIMEOUT  seconds per SQL statement (default 60)
    WMS_AGENT_MAX_ITER       tool-call rounds per question (default 25)
    WMS_AGENT_FALLBACKS      1 (default) = server-side refusal fallback on; 0 = off
    WMS_AGENT_SKILL_DIR      folder holding SKILL.md + references\ (default ..\skill\wms-knowledge)
    WMS_AGENT_CLAUDE_MD      a CLAUDE.md whose "## WMS cheat sheet" section is added to the prompt
    WMS_AGENT_MEMORY_DIR     folder holding the memory bank (wms_memory_mcp_server.py + wms_memory_core.py);
                             memory tools are skipped when absent
    WMS_AGENT_KNOWLEDGE_DIR  folder holding knowledge_mcp_server.py + knowledge.db; skipped when absent
    WMS_AGENT_DEFAULT_SERVER server name Claude should query by default (default prod)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRANSCRIPT_DIR = HERE / "transcripts"


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE, # comments). Real env vars win over the file."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(HERE / ".env")


def _dir(env: str, default: Path | None, must_have: str) -> Path | None:
    raw = os.getenv(env)
    cand = Path(raw) if raw else default
    return cand if cand and (cand / must_have).exists() else None


SKILL_DIR = _dir("WMS_AGENT_SKILL_DIR", HERE.parent / "skill" / "wms-knowledge", "SKILL.md")
CLAUDE_MD = Path(os.getenv("WMS_AGENT_CLAUDE_MD", HERE.parent / "claude" / "CLAUDE.md.example"))
MEMORY_DIR = _dir("WMS_AGENT_MEMORY_DIR", None, "wms_memory_mcp_server.py")
KNOWLEDGE_DIR = _dir("WMS_AGENT_KNOWLEDGE_DIR", None, "knowledge_mcp_server.py")

MODEL = os.getenv("WMS_AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("WMS_AGENT_EFFORT", "high")
MAX_TOKENS = 32000                     # streaming, so a large ceiling costs nothing unless used
MAX_ROWS_DEFAULT = int(os.getenv("WMS_AGENT_MAX_ROWS", "200"))
MAX_ROWS_HARD_CAP = 1000
QUERY_TIMEOUT = int(os.getenv("WMS_AGENT_QUERY_TIMEOUT", "60"))
MAX_ITERATIONS = int(os.getenv("WMS_AGENT_MAX_ITER", "25"))
FALLBACKS_ON = os.getenv("WMS_AGENT_FALLBACKS", "1") == "1" and not os.getenv("ANTHROPIC_BASE_URL")
DEFAULT_SERVER = os.getenv("WMS_AGENT_DEFAULT_SERVER", "prod")
ODBC_DRIVER = os.getenv("WMS_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

# Price table ($ per million tokens) for the cost line printed after each turn.
# Cache write is 1.25x input, cache read is the listed value.
PRICES = {
    "claude-opus-5-5":   {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20},
    "claude-haiku-5-5":  {"in": 0.10, "out": 0.50,  "cache_read": 0.01},
}


def load_servers() -> dict:
    """Server registry: WMS_AGENT_SERVERS JSON, else built from WMS_PROD_SERVER / WMS_TEST_SERVER."""
    raw = os.getenv("WMS_AGENT_SERVERS")
    if raw:
        return json.loads(raw)
    db = os.getenv("WMS_DATABASE", "WMS")
    servers = {}
    if os.getenv("WMS_PROD_SERVER"):
        servers["prod"] = {"host": os.environ["WMS_PROD_SERVER"], "db": db, "production": True, "cred_prefix": "WMS"}
    if os.getenv("WMS_TEST_SERVER"):
        servers["test"] = {"host": os.environ["WMS_TEST_SERVER"], "db": db, "production": False, "cred_prefix": "WMS"}
    return servers or {"prod": {"host": "<PROD_HOST>", "db": db, "production": True, "cred_prefix": "WMS"}}


SERVERS = load_servers()
