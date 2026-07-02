"""AI layer: MCP server exposing the aiops loop to an AI assistant.

Register with Claude Code:
    claude mcp add warehouse_aiops -s user -- python <path-to>/aiops_mcp_server.py

The assistant becomes the incident console: it can scan, read incidents with
full evidence, explain diagnoses in plain language, and — ONLY when the human
explicitly says so — approve or reject a proposal. The same state machine
guards everything: nothing executes without a human decision; the AI is the
interface, not the authority.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from core import engine, store

mcp = FastMCP("warehouse-aiops")


@mcp.tool()
def scan_now() -> dict:
    """Run all playbook detectors now. Returns newly opened incidents (each
    fully diagnosed with a remediation proposal). Read-only against the
    warehouse; auto-closes acknowledged incidents whose condition cleared."""
    created = [i.brief() for i in engine.scan()]
    return {"new_incidents": created, "count": len(created)}


@mcp.tool()
def list_incidents(state: str = "") -> list[dict]:
    """List incidents, optionally filtered by state (PROPOSED, ACKNOWLEDGED,
    VERIFIED, REJECTED, FAILED, CLOSED)."""
    return [i.brief() for i in store.all_incidents(state.upper() or None)]


@mcp.tool()
def get_incident(iid: str) -> dict:
    """Full incident detail: evidence, diagnosis, the exact proposed fix with
    its verification contract and risk note, execution and verification
    results. Use this to review before any approval decision."""
    inc = store.get(iid)
    return inc.full() if inc else {"error": f"no such incident: {iid}"}


@mcp.tool()
def approve_incident(iid: str, operator: str = "operator-via-ai") -> dict:
    """Execute an incident's proposed fix (transactional, read-back verified,
    rolled back on mismatch) or acknowledge a manual proposal.

    GOVERNANCE: call this ONLY when the human user has explicitly instructed
    approval of this specific incident in this conversation — never on your
    own initiative, and never inferred from a general request.
    """
    return engine.approve(iid, operator).full()


@mcp.tool()
def reject_incident(iid: str, reason: str = "", operator: str = "operator-via-ai") -> dict:
    """Reject a proposed incident (records the reason to the runbook).
    GOVERNANCE: only on explicit human instruction, as with approval."""
    return engine.reject(iid, reason, operator).full()


@mcp.tool()
def read_runbook() -> str:
    """The runbook: every resolved/acknowledged/rejected incident with root
    cause and action taken — the organizational memory. Consult it when
    diagnosing something that looks familiar."""
    try:
        return open(store.RUNBOOK, encoding="utf-8").read()
    except FileNotFoundError:
        return "(runbook is empty — no incidents closed yet)"


if __name__ == "__main__":
    mcp.run()
