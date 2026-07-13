"""warehouse-twin demo: baseline day vs. a what-if scenario, side by side.

    python run_demo.py                 # baseline vs '+2 FROZEN pickers'
    python run_demo.py --growth 20     # baseline vs +20% order volume
"""
import argparse
import sys

from twin import load_params, run_scenario

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def flat(report: dict) -> dict:
    z = report["zones"]
    return {
        "orders completed": f'{report["orders"]["completed"]}/{report["orders"]["arrived"]} ({report["orders"]["completion_pct"]}%)',
        "on-time by ship cutoff": f'{report["service_level"]["shipped_by_cutoff"]}/{report["service_level"]["cutoff_eligible_orders"]} ({report["service_level"]["on_time_pct"]}%)',
        "avg cycle (arrival->done)": f'{report["cycle_time_min"]["arrival_to_complete_avg"]} min',
        "p90 cycle (arrival->done)": f'{report["cycle_time_min"]["arrival_to_complete_p90"]} min',
        "waves released": report["waves_released"],
        **{
            f"{name} util / queue left": f'{zz["utilization_pct"]}% / {zz["queue_remaining"]}'
            for name, zz in z.items()
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params/representative_dc.json")
    ap.add_argument("--growth", type=int, default=None,
                    help="compare baseline vs +N%% order volume instead of +2 frozen pickers")
    args = ap.parse_args()

    p = load_params(args.params)
    baseline = run_scenario(p)

    if args.growth:
        label = f"+{args.growth}% order volume"
        overrides = {"orders_per_day": int(p.orders_per_day * (1 + args.growth / 100))}
    else:
        label = "+2 FROZEN pickers"
        overrides = {"zones.FROZEN.pickers": p.zones["FROZEN"].pickers + 2}
    scenario = run_scenario(p, overrides)

    b, s = flat(baseline), flat(scenario)
    w = max(len(k) for k in b)
    print(f"\n=== {baseline['site']} — simulated day ===\n")
    print(f'{"KPI":<{w}}   {"BASELINE":<28} {label}')
    print("-" * (w + 60))
    for k in b:
        print(f"{k:<{w}}   {str(b[k]):<28} {s[k]}")
    print()


if __name__ == "__main__":
    main()
