"""AI copilot layer: MCP server exposing the warehouse twin to AI assistants.

Run (or register with your MCP client):
    python -m twin.mcp_server

Tools:
    describe_twin()            -> parameters + calibration provenance
    run_twin_scenario(...)     -> KPI report for one scenario (replicated)
    compare_twin_scenarios(...)-> labeled side-by-side scenarios
    sweep_twin_parameter(...)  -> one parameter swept over several values

With these four primitives an AI assistant can design and run experiments
conversationally: "find the smallest FROZEN crew that survives +30% volume"
becomes a sweep + comparison it composes on its own. The simulation stays
deterministic and local; the AI is the experiment designer and narrator.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from twin.params import load_params
from twin.engine import run_scenario

DEFAULT_PARAMS = Path(__file__).resolve().parent.parent / "params" / "representative_dc.json"

mcp = FastMCP("warehouse-twin")


def _params():
    return load_params(DEFAULT_PARAMS)


@mcp.tool()
def describe_twin() -> dict:
    """Describe the simulated DC: all parameters, their meaning, and data
    provenance (which values are empirical vs. benchmark-set). Call this first
    to learn what can be overridden."""
    p = _params()
    return {
        "site": p.site_name,
        "parameters": p.raw,
        "override_syntax": 'dotted paths, e.g. {"zones.FROZEN.pickers": 2, "orders_per_day": 576}',
        "provenance": {
            "arrival_weights_by_hour": "empirical (normalized 14-day host-import curve)",
            "lines_per_order": "empirical (30 days, 8 sites)",
            "wave_interval_min": "empirical cadence",
            "zones.*.share": "representative grocery mix",
            "zones.*.pick_rate_lph": "benchmark-set (source timestamps are date-grain); tune freely",
            "zones.*.pickers": "sized for realistic utilization vs. empirical volume",
        },
        "kpis": ["completion_pct", "on_time_pct", "cycle_avg_min", "cycle_p90_min",
                 "per-zone utilization_pct / queue_remaining"],
    }


@mcp.tool()
def run_twin_scenario(overrides: str = "{}", replications: int = 10) -> dict:
    """Run one scenario and return its KPI report (mean +/- stdev over
    `replications` random seeds).

    Args:
        overrides: JSON object of dotted-path parameter overrides,
                   e.g. '{"zones.FROZEN.pickers": 2}'. "{}" = baseline.
        replications: seeds to average over (default 10).
    """
    ov = json.loads(overrides) if overrides else {}
    return run_scenario(_params(), ov or None, replications=replications)


@mcp.tool()
def compare_twin_scenarios(scenarios: str, replications: int = 10) -> dict:
    """Run several labeled scenarios and return them side by side.

    Args:
        scenarios: JSON list of {"label": str, "overrides": {dotted-path: value}}.
                   Include {"label": "baseline", "overrides": {}} to anchor.
        replications: seeds per scenario (default 10).
    """
    spec = json.loads(scenarios)
    p = _params()
    return {
        s["label"]: run_scenario(p, s.get("overrides") or None, replications=replications)
        for s in spec
    }


@mcp.tool()
def sweep_twin_parameter(param_path: str, values: str, replications: int = 5) -> dict:
    """Sweep one parameter over several values (all else baseline) — the tool
    for "how many pickers do we need?" style questions.

    Args:
        param_path: dotted path, e.g. "zones.FROZEN.pickers" or "orders_per_day".
        values: JSON list of values to try, e.g. "[1, 2, 3, 4]".
        replications: seeds per value (default 5).
    """
    vals = json.loads(values)
    p = _params()
    return {
        str(v): run_scenario(p, {param_path: v}, replications=replications)
        for v in vals
    }


@mcp.tool()
def evaluate_gtp_automation(stations: int, rate_lph: float, line_coverage: float,
                            revised_pickers: str, capex_usd: float,
                            wage_usd_hr: float = 22.0, opex_usd_yr: float = 0.0,
                            replications: int = 10) -> dict:
    """Full automation business case: simulate a goods-to-person (GTP) zone with
    revised conventional staffing, compare service vs. baseline, and compute
    labor-savings payback on the capex.

    Args:
        stations: staffed GTP pick stations.
        rate_lph: lines per station-hour (typical GTP: 300-700).
        line_coverage: fraction of all lines the automated system covers (SKU
                       coverage), e.g. 0.45.
        revised_pickers: JSON object of conventional staffing AFTER automation,
                         e.g. '{"DRY": 2, "COOLER": 1, "FROZEN": 1}'.
        capex_usd: installed cost of the system.
        wage_usd_hr / opex_usd_yr: economics assumptions.
        replications: seeds per scenario.
    """
    from twin.economics import payback_analysis

    p = _params()
    baseline = run_scenario(p, replications=replications)
    overrides: dict = {
        "automation.enabled": True,
        "automation.stations": stations,
        "automation.rate_lph": rate_lph,
        "automation.line_coverage": line_coverage,
    }
    for zone, n in json.loads(revised_pickers).items():
        overrides[f"zones.{zone}.pickers"] = n
    scenario = run_scenario(p, overrides, replications=replications)

    shift_hours = p.pick_shift_end_hr - p.pick_shift_start_hr
    econ = payback_analysis(baseline, scenario, capex_usd, wage_usd_hr,
                            opex_usd_yr, shift_hours=shift_hours)
    return {"baseline": baseline, "scenario": scenario, "business_case": econ}


if __name__ == "__main__":
    mcp.run()
