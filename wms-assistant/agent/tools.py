"""
tools.py - the tools the agent hands to Claude. All read-only.

    read_reference     one of the wms-knowledge reference files (always available)
    run_sql            one SELECT against a configured server, through guard.py, READ UNCOMMITTED,
                       row-capped; recorded in the memory bank when one is configured
    recall             facts + past SQL from the memory bank          (needs WMS_AGENT_MEMORY_DIR)
    schema             cached column list, live refresh when stale    (needs WMS_AGENT_MEMORY_DIR)
    find_column        which cached tables carry a column like this   (needs WMS_AGENT_MEMORY_DIR)
    object_definition  proc/view/function body, optionally grep-filtered (needs WMS_AGENT_MEMORY_DIR)
    recent_changes     the memory bank's write ledger                 (needs WMS_AGENT_MEMORY_DIR)
    search_knowledge   hybrid search over the local document index   (needs WMS_AGENT_KNOWLEDGE_DIR)

The memory bank and the document index are the MCP servers described in
ai-ops-playbook/04-memory-architecture.md; their modules are imported directly so there is
one implementation shared with the MCP servers. Both are optional: all_tools() only
registers the tools whose backing folder exists.
"""
from __future__ import annotations

import datetime as dt
import decimal
import logging
import os
import re
import sys
import time

from anthropic import beta_tool

import config
import guard

# Quiet the sentence-transformers / huggingface chatter when a document index loads.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
for _name in ("httpx", "sentence_transformers", "huggingface_hub", "transformers"):
    logging.getLogger(_name).setLevel(logging.WARNING)

core = mem = None
if config.MEMORY_DIR:
    sys.path.insert(0, str(config.MEMORY_DIR))
    import wms_memory_core as core          # noqa: E402
    import wms_memory_mcp_server as mem     # noqa: E402  (the FastMCP decorators return the plain functions)

_knowledge = None


def _server(name: str) -> str:
    s = name or config.DEFAULT_SERVER
    if s not in config.SERVERS:
        raise ValueError(f"Unknown server '{s}'. Known: {', '.join(sorted(config.SERVERS))}")
    return s


def _odbc_val(v: str) -> str:
    """ODBC connection-string quoting: braces, with any closing brace doubled."""
    return "{" + str(v).replace("}", "}}") + "}"


def _connect(server: str):
    """pyodbc connection to a configured server, autocommit, credentials from env."""
    import pyodbc
    s = config.SERVERS[server]
    prefix = s.get("cred_prefix", "WMS")
    user, pwd = os.getenv(f"{prefix}_USER"), os.getenv(f"{prefix}_PASS")
    if not (user and pwd):
        raise RuntimeError(f"{prefix}_USER / {prefix}_PASS not set")
    cs = (f"Driver={{{config.ODBC_DRIVER}}};Server={s['host']};Database={s.get('db', 'WMS')};"
          f"UID={_odbc_val(user)};PWD={_odbc_val(pwd)};Encrypt=yes;TrustServerCertificate=yes;APP=wms_agent;")
    return pyodbc.connect(cs, autocommit=True, timeout=15)


def _cell(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, dt.datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(v.normalize()) if v == v.to_integral() else f"{v:f}"
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "0x" + bytes(v).hex()[:40]
    s = str(v)
    return s if len(s) <= 120 else s[:117] + "..."


def _record(server: str, stmt: str, result: dict | None = None, error: str | None = None) -> None:
    """Feed the memory bank exactly like the MCP capture hook does. Silent when no bank is configured."""
    if core is None:
        return
    try:
        con = core.connect(core.db_path())
        core.record_query(con, server=server, sql=stmt, session_id="agent", result=result, error=error)
        con.close()
    except Exception:
        pass


@beta_tool(eager_input_streaming=True)
def run_sql(sql: str, server: str = "", max_rows: int = 0) -> str:
    """Run ONE read-only SELECT (or WITH ... SELECT) against a WMS SQL Server and return the rows as a
    tab-separated table. Writes, EXEC, DDL, batches and system procedures are refused. Runs under
    READ UNCOMMITTED, so WITH (NOLOCK) is optional. Use TOP and date filters on large tables
    (t_tran_log, t_pick_detail, t_stored_item, t_al_host_*). Other databases on the same instance are
    reachable with three-part names (REPOSITORY.dbo.t_app_field).

    Args:
        sql: the SELECT statement. One statement only.
        server: a configured server name (e.g. prod, test); default = the session's server.
        max_rows: rows to return (default 200, hard cap 1000). Extra rows are dropped and flagged.
    """
    srv = _server(server)
    try:
        stmt = guard.check(sql)
    except guard.GuardError as exc:
        return f"REFUSED: {exc}"
    cap = min(max_rows or config.MAX_ROWS_DEFAULT, config.MAX_ROWS_HARD_CAP)
    t0 = time.perf_counter()
    info = config.SERVERS[srv]
    result = {"server": info["host"], "database": info.get("db", "WMS"), "result_sets": []}
    cn = None
    try:
        cn = _connect(srv)
        cn.timeout = config.QUERY_TIMEOUT
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.execute(stmt)
        if cur.description is None:
            return "(statement returned no result set)"
        columns = [d[0] for d in cur.description]
        raw = cur.fetchmany(cap + 1)
        truncated = len(raw) > cap
        rows = raw[:cap]
        ms = round((time.perf_counter() - t0) * 1000)
        result["result_sets"].append({"type": "rows", "row_count": len(rows), "columns": columns,
                                      "rows": [{c: _cell(v) for c, v in zip(columns, r)} for r in rows[:3]]})
        _record(srv, stmt, result=result)
        head = (f"{srv} ({result['server']}/{result['database']}) {len(rows)} row(s)"
                f"{' TRUNCATED at ' + str(cap) if truncated else ''} in {ms} ms"
                f"{'  [PRODUCTION]' if info.get('production') else ''}")
        lines = [head, "\t".join(columns)]
        lines += ["\t".join(_cell(v) for v in r) for r in rows]
        return "\n".join(lines)
    except Exception as exc:
        _record(srv, stmt, error=str(exc)[:500])
        return f"SQL error on {srv}: {exc}"
    finally:
        try:
            if cn is not None:
                cn.close()
        except Exception:
            pass


@beta_tool(eager_input_streaming=True)
def recall(question: str) -> str:
    """Search the WMS memory bank first: verified facts, past SQL that answered similar questions
    (with how often it was reused and what it returned), and whether the named tables/procs are cached.

    Args:
        question: the question or the thing you are about to look up.
    """
    return mem.recall(question, max_chars=2500)


@beta_tool(eager_input_streaming=True)
def schema(table: str, server: str = "") -> str:
    """Column list of a table (name, type, nullability) from the cache; refreshes live when missing or stale.
    Cheaper and more reliable than guessing column names.

    Args:
        table: 't_order' or 'dbo.t_order'.
        server: default = the session's server.
    """
    return mem.schema(table, server=_server(server))


@beta_tool(eager_input_streaming=True)
def find_column(column_like: str, server: str = "") -> str:
    """Which cached tables have a column whose name contains this text (case-insensitive).

    Args:
        column_like: e.g. 'hu_id', 'expir', 'wh_id'.
        server: default = the session's server.
    """
    return mem.find_column(column_like, server=_server(server))


@beta_tool(eager_input_streaming=True)
def object_definition(name: str, server: str = "", grep: str = "", refresh: bool = False) -> str:
    """Body of a stored procedure, view, function or trigger from the version cache. With grep, only the
    matching lines with 3 lines of context are returned, which is much cheaper for long procs.

    Args:
        name: 'usp_afo_hold_wave' or 'dbo.usp_afo_hold_wave'.
        server: default = the session's server.
        grep: regex; return only matching line windows.
        refresh: re-read the live definition (read-only) and store a new version if it changed.
    """
    return mem.object(name, server=_server(server), grep=grep, refresh=refresh)


@beta_tool(eager_input_streaming=True)
def recent_changes(server: str = "", project: str = "", since: str = "", production_only: bool = False) -> str:
    """The memory bank's write ledger: every INSERT/UPDATE/DELETE/DDL/EXEC the team ran through the WMS MCP
    servers, newest first, with the project tag. Use it to answer 'what changed recently' questions.

    Args:
        server: filter by server name.
        project: substring of the '-- project:' tag.
        since: ISO date, e.g. '2026-09-01'.
        production_only: only production writes.
    """
    return mem.changes(server=server, project=project, since=since, production_only=production_only, limit=30)


@beta_tool(eager_input_streaming=True)
def search_knowledge(query: str, top_k: int = 6) -> str:
    """Hybrid keyword + semantic search over the team's documents: runbooks, issue log, deploy records,
    rollback scripts, design docs, memory notes. Use it for 'has this happened before', 'why was it built
    this way', and 'where is the script for X'.

    Args:
        query: free-text question or keywords.
        top_k: number of passages to return (default 6).
    """
    global _knowledge
    if _knowledge is None:
        sys.path.insert(0, str(config.KNOWLEDGE_DIR))
        import knowledge_mcp_server  # noqa: E402
        _knowledge = knowledge_mcp_server
    res = _knowledge.search_knowledge(query, top_k=top_k)
    if not res.get("results"):
        return f"no passages match '{query}' ({res.get('mode')})"
    out = [f"{res['result_count']} passage(s), {res['mode']} search"]
    for r in res["results"]:
        body = re.sub(r"\s+", " ", r["content"]).strip()
        out.append(f"--- {r['document']} | {r['heading'] or '(top)'} | {r['path']}\n{body[:900]}")
    return "\n".join(out)


def _reference_files() -> list:
    if config.SKILL_DIR is None:
        return []
    return sorted((config.SKILL_DIR / "references").glob("*.md"))


@beta_tool(eager_input_streaming=True)
def read_reference(name: str = "") -> str:
    """Read one of the WMS domain reference files (the decoded knowledge: codes, schema traps, ERP integration,
    allocation and autowave, receiving/RF, cleanup recipes, design-database development, customization
    inventory). Call with no name to list them. Read the matching file BEFORE answering a behaviour or
    design question.

    Args:
        name: a number ('03') or part of the file name ('integration', 'cleanup'). Empty lists the files.
    """
    files = _reference_files()
    if not name:
        return "\n".join(f.name for f in files) or "no reference files found"
    key = name.strip().lower()
    hits = [f for f in files if f.name.lower().startswith(key) or key in f.name.lower()]
    if not hits:
        return f"no reference matches '{name}'. Available: " + ", ".join(f.name for f in files)
    return hits[0].read_text(encoding="utf-8")


def all_tools() -> list:
    tools = [read_reference, run_sql]
    if mem is not None:
        tools += [recall, schema, find_column, object_definition, recent_changes]
    if config.KNOWLEDGE_DIR is not None:
        tools.append(search_knowledge)
    return tools
