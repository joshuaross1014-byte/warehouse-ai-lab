"""Launcher for the warehouse-twin MCP server (run from any cwd).

Register with Claude Code:
    claude mcp add warehouse_twin -s user -- python <path-to>/twin_mcp_server.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from twin.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
