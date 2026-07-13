"""Automation business-case math: labor cost, savings, and payback.

Compares a baseline scenario against an automation scenario (e.g. a GTP zone
with reduced conventional staffing) and answers the consulting question:
does the labor saved pay for the capex — and does service hold?

Works on the aggregated (replicated) report format from `run_scenario`.
"""
from __future__ import annotations


def payback_analysis(baseline: dict, scenario: dict, capex_usd: float,
                     wage_usd_hr: float = 22.0, opex_usd_yr: float = 0.0,
                     shift_hours: float = 16.0, operating_days: int = 360) -> dict:
    """Labor-savings payback for an automation scenario vs. baseline.

    Staffed positions = pickers per zone (GTP stations count as staffed pick
    stations). Savings = (baseline daily labor - scenario daily labor) scaled
    to a year, minus automation opex. Service deltas are reported alongside —
    a payback that destroys the ship cutoff is not a business case.
    """
    def staffed(report: dict) -> int:
        return sum(z["pickers"] for z in report["zones"].values())

    def mean(report: dict, key: str):
        v = report.get(key)
        return v["mean"] if isinstance(v, dict) and "mean" in v else v

    base_heads, scen_heads = staffed(baseline), staffed(scenario)
    base_day = base_heads * shift_hours * wage_usd_hr
    scen_day = scen_heads * shift_hours * wage_usd_hr
    savings_yr = (base_day - scen_day) * operating_days - opex_usd_yr

    return {
        "staffing": {"baseline_positions": base_heads, "scenario_positions": scen_heads,
                     "positions_saved": base_heads - scen_heads},
        "labor_cost_usd": {"baseline_per_day": round(base_day),
                           "scenario_per_day": round(scen_day),
                           "annual_savings_net_of_opex": round(savings_yr)},
        "investment": {"capex_usd": capex_usd, "opex_usd_yr": opex_usd_yr,
                       "payback_years": round(capex_usd / savings_yr, 2) if savings_yr > 0 else None},
        "service_delta": {
            "on_time_pct": {"baseline": mean(baseline, "on_time_pct"),
                            "scenario": mean(scenario, "on_time_pct")},
            "completion_pct": {"baseline": mean(baseline, "completion_pct"),
                               "scenario": mean(scenario, "completion_pct")},
            "cycle_avg_min": {"baseline": mean(baseline, "cycle_avg_min"),
                              "scenario": mean(scenario, "cycle_avg_min")},
        },
        "assumptions": {"wage_usd_hr": wage_usd_hr, "shift_hours_per_day": shift_hours,
                        "operating_days_per_year": operating_days},
    }
