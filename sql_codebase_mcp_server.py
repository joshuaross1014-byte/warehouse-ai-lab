"""MCP server: let an AI assistant answer impact questions about a SQL codebase.

Point it at a graph produced by `python -m sqlcodebase index ...`:

    claude mcp add sql_codebase -s user \
        -e SQL_CODEBASE_GRAPH=/path/to/graph.json \
        -- python /path/to/sql_codebase_mcp_server.py

Then ask things like: "what breaks if I change t_order?", "who writes to the
wave table?", "which procedures are the riskiest to touch?"
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from sqlcodebase import graph as G

GRAPH_PATH = os.getenv("SQL_CODEBASE_GRAPH", "graph.json")

mcp = FastMCP("sql-codebase")
_graph = None


def g() -> dict:
    global _graph
    if _graph is None:
        _graph = G.load(GRAPH_PATH)
    return _graph


@mcp.tool()
def codebase_stats() -> dict:
    """Object and edge counts for the indexed codebase, including how many
    objects contain dynamic SQL (where static analysis is incomplete)."""
    return G.stats(g())


@mcp.tool()
def object_info(name: str) -> dict:
    """Everything about one object: what it calls/reads/writes, and what
    calls/reads/writes it. Flags dynamic SQL. Use before modifying anything."""
    return G.object_info(g(), name)


@mcp.tool()
def impact_of(name: str, max_depth: int = 0) -> dict:
    """THE question: everything that transitively depends on this object —
    what could break if it changes. Grouped by dependency distance; lists any
    dependents whose dynamic SQL makes the analysis incomplete. max_depth 0 =
    unlimited."""
    return G.impact(g(), name, max_depth)


@mcp.tool()
def table_usage(table: str) -> dict:
    """All writers and readers of a table — the blast radius of a schema or
    data change at one glance."""
    return G.table_usage(g(), table)


@mcp.tool()
def hotspots(top: int = 10) -> dict:
    """The most-depended-on objects (touch with care) and the widest-reaching
    procedures (touch many things). The codebase's risk map."""
    return G.hotspots(g(), top)


@mcp.tool()
def search_objects(term: str) -> list[dict]:
    """Find objects by name substring."""
    return G.search(g(), term)


if __name__ == "__main__":
    mcp.run()
