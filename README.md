# sql-codebase-mcp

**Ask an AI "what breaks if I change this table?" — and get a real answer.**

Point this tool at any SQL Server codebase (a live database or a folder of `.sql`
files). It parses every procedure, view, function, and trigger, builds the full
dependency graph — *calls, reads, writes, fires-on* — and serves it over
[MCP](https://modelcontextprotocol.io/) so an AI assistant can do impact analysis on a
legacy codebase in milliseconds:

```
you:    what breaks if I change t_order?
ai:     74 objects transitively depend on it — 67 directly. The riskiest are the
        5 wave-planning procedures that write it, plus 2 dependents contain
        dynamic SQL, so static analysis is incomplete there — review those by hand.
```

Built because I inherited a **500+ stored-procedure WMS codebase with no
documentation** — before you change a 500-line procedure in production, you need to
know what calls it and what it touches. This turns that from archaeology into a lookup.

## Quickstart (60 seconds, demo corpus included)

```bash
python -m sqlcodebase index demo/           # parse -> graph.json
python -m sqlcodebase impact orders         # what depends on the orders table?
python -m sqlcodebase table inventory       # who reads/writes it?
python -m sqlcodebase hotspots              # the codebase's risk map
python -m sqlcodebase info usp_ship_order   # one object, both directions
```

Stdlib only. (`pyodbc` needed only for live-database extraction; `mcp` only for the server.)

## Index your own codebase

**From a live SQL Server** (read-only; connection via env vars, nothing in code):

```bash
export SQLCB_SERVER=... SQLCB_DB=... SQLCB_USER=... SQLCB_PASS=...
python scripts/extract_mssql.py extracted_sql/     # dumps sys.sql_modules + table stubs
python -m sqlcodebase index extracted_sql/ -o graph.json
```

**From source files:** `python -m sqlcodebase index path/to/sql/` — works on a repo,
a schema dump, or a single script.

## The AI layer

```bash
claude mcp add sql_codebase -s user \
    -e SQL_CODEBASE_GRAPH=/path/to/graph.json \
    -- python /path/to/sql_codebase_mcp_server.py
```

Six tools: `codebase_stats`, `object_info`, `impact_of`, `table_usage`, `hotspots`,
`search_objects`. The assistant composes them — "is it safe to add a column to the
wave table?" becomes usage + impact + hotspot lookups it runs itself.

## Honesty by design

Static analysis of T-SQL has hard limits, and the tool tells you where:

- **Dynamic SQL** (`EXEC(...)`, `sp_executesql`) can't be statically resolved. Objects
  containing it are **flagged**, and `impact_of` lists any flagged dependents in its
  answer — so "the graph says you're safe" is never silently wrong.
- Parsing is pragmatic regex over cleaned source (comments/strings stripped), with a
  keyword guard and alias filtering — not a full grammar. Field-tested against a
  production WMS codebase (515 procedures, 413 tables, ~3,500 edges) where it correctly
  mapped writer/reader sets for core tables; expect *good*, not *perfect*, and verify
  the critical paths.

## Architecture

```
sqlcodebase/parse.py   T-SQL reference scanner (clean -> scan -> normalize)
sqlcodebase/graph.py   graph build/persist + impact / usage / hotspot queries
sqlcodebase/__main__.py CLI (index · stats · info · impact · table · hotspots · search)
scripts/extract_mssql.py  live-DB extractor (sys.sql_modules, read-only)
sql_codebase_mcp_server.py  the AI interface
demo/                  miniature order-management corpus
```

## Roadmap

- [x] v0.1 — parser, graph, impact queries, CLI, demo corpus, live extractor, MCP server
- [ ] Column-level lineage (which procedures touch `orders.status` specifically)
- [ ] `sys.sql_expression_dependencies` cross-check in live mode (engine-reported edges vs parsed)
- [ ] Graph diff between two indexes (what did this release change?)
- [ ] HTML visual explorer

## Author

Joshua Ross — ERP & WMS systems analyst (SAP Business One, Körber/Infios HighJump/KCloud),
B.S.E. Industrial Engineering. Companion projects:
[warehouse-twin](https://github.com/joshuaross1014-byte/warehouse-twin) ·
[warehouse-aiops](https://github.com/joshuaross1014-byte/warehouse-aiops) ·
[claude-ops-toolkit](https://github.com/joshuaross1014-byte/claude-ops-toolkit)
