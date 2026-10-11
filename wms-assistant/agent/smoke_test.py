"""
smoke_test.py - exercise the guard, the system prompt and every registered tool WITHOUT calling the Claude API.

    python smoke_test.py            runs everything; SQL checks use the 'test' server if WMS_USER/WMS_PASS are set
    python smoke_test.py --prod     also runs one SELECT against 'prod' (read-only)

Exit code 0 = all checks passed.
"""
from __future__ import annotations

import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config  # noqa: E402
import guard   # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


def run(name: str, fn, expect=None):
    try:
        out = fn()
        ok = True if expect is None else expect(out)
        check(name, ok, (out if isinstance(out, str) else str(out))[:160].replace("\n", " | "))
        return out
    except Exception as exc:
        check(name, False, f"{type(exc).__name__}: {exc}")
        return None


def _expect_block(sql: str) -> bool:
    try:
        guard.check(sql)
        return False
    except guard.GuardError:
        return True


def main() -> int:
    prod = "--prod" in sys.argv

    # ---- guard ----------------------------------------------------------------
    good = ["SELECT TOP 5 * FROM dbo.t_order WITH (NOLOCK)",
            "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
            "SELECT name FROM sys.objects WHERE name LIKE '%update%'  -- comment with DELETE in it",
            "SELECT 'drop table t' AS s"]
    bad = ["UPDATE t_order SET status='B'", "SELECT * INTO bak FROM t_order", "EXEC usp_delete_wave 'WH','x'",
           "SELECT 1; DELETE t_order", "SELECT 1\nGO\nSELECT 2", "DELETE FROM t_order", "SELECT * FROM OPENROWSET('x','y','z')",
           "SELECT 1 FROM t WHERE 1=1 WAITFOR DELAY '00:00:05'", "EXEC msdb.dbo.sp_help_job"]
    for s in good:
        run(f"guard allows: {s[:45]}", lambda s=s: guard.check(s))
    for s in bad:
        run(f"guard blocks: {s[:45]}", lambda s=s: _expect_block(s), expect=lambda o: o is True)

    # ---- system prompt + tools (no API) ---------------------------------------
    import agent
    import tools
    sysblocks = run("system prompt builds", agent.build_system, expect=lambda b: len(b[0]["text"]) > 1000)
    if sysblocks:
        print(f"      system prompt {len(sysblocks[0]['text']):,} chars (~{len(sysblocks[0]['text'])//4:,} tokens)")
    names = [t.name for t in tools.all_tools()]
    run("tool list", lambda: names, expect=lambda l: "run_sql" in l and "read_reference" in l)
    run("read_reference list", lambda: tools.read_reference.call({"name": ""}), expect=lambda o: "01-environment" in o)
    run("read_reference 06", lambda: tools.read_reference.call({"name": "06"}), expect=lambda o: "Stuck wave" in o)
    if "recall" in names:
        run("recall", lambda: tools.recall.call({"question": "t_order status codes"}), expect=lambda o: isinstance(o, str) and o)
        run("schema t_order", lambda: tools.schema.call({"table": "t_order"}), expect=lambda o: "order_number" in o or "not" in o)
        run("recent_changes", lambda: tools.recent_changes.call({"production_only": True}), expect=lambda o: isinstance(o, str))
    else:
        check("memory tools", True, "skipped: WMS_AGENT_MEMORY_DIR not configured")
    if "search_knowledge" in names:
        run("search_knowledge", lambda: tools.search_knowledge.call({"query": "stuck wave hold picking has started", "top_k": 2}),
            expect=lambda o: isinstance(o, str))
    else:
        check("search_knowledge", True, "skipped: WMS_AGENT_KNOWLEDGE_DIR not configured")

    # ---- live SQL (read-only) --------------------------------------------------
    if os.getenv("WMS_USER") and os.getenv("WMS_PASS") and "test" in config.SERVERS:
        run("run_sql refuses a write (test)", lambda: tools.run_sql.call({"sql": "UPDATE t_order SET status='B' WHERE 1=0", "server": "test"}),
            expect=lambda o: o.startswith("REFUSED"))
        run("run_sql SELECT on test", lambda: tools.run_sql.call(
            {"sql": "SELECT TOP 3 wh_id, order_number, status FROM dbo.t_order ORDER BY order_number DESC", "server": "test", "max_rows": 3}),
            expect=lambda o: "row(s)" in o and "status" in o)
        run("run_sql cap + truncation flag", lambda: tools.run_sql.call(
            {"sql": "SELECT TOP 5 wh_id FROM dbo.t_whse", "server": "test", "max_rows": 2}),
            expect=lambda o: "TRUNCATED" in o)
        if prod and "prod" in config.SERVERS:
            run("run_sql SELECT on prod", lambda: tools.run_sql.call(
                {"sql": "SELECT COUNT(*) AS whs FROM dbo.t_whse WITH (NOLOCK)", "server": "prod"}),
                expect=lambda o: "PRODUCTION" in o and "whs" in o)
    else:
        check("run_sql", True, "skipped: WMS_USER/WMS_PASS or a 'test' server not configured")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
