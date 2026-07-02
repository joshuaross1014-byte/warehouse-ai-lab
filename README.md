# warehouse-twin

A **digital twin of a grocery distribution center** — a zero-dependency discrete-event
simulation grounded in the operating statistics of a real multi-site WMS, built to answer
the questions warehouse operators and automation consultants actually ask:

> *"What happens to cutoff performance if volume grows 20%?"*
> *"Where's the bottleneck — and does adding two frozen-zone pickers fix it?"*
> *"What does a goods-to-person system need to hit for payback?"*

```
$ python run_demo.py

=== DC-EAST (representative) — simulated day ===

KPI                         BASELINE                     +2 FROZEN pickers
-------------------------------------------------------------------------------
orders completed            420/480 (87.5%)              428/480 (89.2%)
avg cycle (arrival->done)   101.7 min                    84.3 min
FROZEN util / queue left    92.3% / 18                   32.8% / 0
```

## Why this exists

I run WMS and integration for a real high-volume grocery distribution network
(~515K picks/month across nine temperature-zoned warehouses). Operational questions —
staffing, wave cadence, growth, automation investment — usually get answered by intuition
or spreadsheets. A parameterized simulation answers them with dynamics: queues, variance,
shift boundaries, and bottlenecks that spreadsheets average away.

The end state is an **AI-operated twin**: a copilot that takes the question in plain
English, designs the experiment, runs the simulation, and explains the trade-offs.

## How it works

```
orders (empirical 24h arrival curve)
   └─> unreleased pool ──[ wave release every N min ]──> zone queues
                                                          ├─ DRY    (picker pool)
                                                          ├─ COOLER (picker pool)
                                                          └─ FROZEN (picker pool)
        order completes when all lines picked ──> KPIs: cycle time, on-time %,
                                                  utilization, queue depth
```

- **Engine** (`twin/engine.py`): heapq-driven discrete-event core — no dependencies.
  Orders arrive on an empirical hourly curve; a wave process releases them on a cadence
  (mirroring real WMS wave planning); zone picker pools serve lines FIFO with exponential
  service times inside a pick shift.
- **Parameters as data** (`params/*.json` + `twin/params.py`): every scenario is a JSON
  override, e.g. `{"zones.FROZEN.pickers": 3, "orders_per_day": 576}` — the primitive an
  AI copilot can drive.
- **One-call API**: `run_scenario(params, overrides) -> KPI report`.

## Grounding & calibration (what's real, what's assumed)

Honest provenance matters more than false precision:

| Parameter | Source |
|---|---|
| 24h order-arrival curve | **Empirical** — normalized from 14 days of live host-import timestamps (shape only, volumes removed) |
| Lines per order (~11, lognormal) | **Empirical** — 30 days of order detail across 8 sites (range 6–14 by site) |
| Wave cadence | **Empirical** — ~480 waves/day network-wide, interval-released |
| Zone mix (55/30/15) | Representative of dry/cooler/frozen grocery operations |
| Pick rates (70/55/45 lph) | **Benchmark-set** — source transaction timestamps are date-grain, so per-hour rates aren't derivable; set from operator-day counts + industry ranges, flagged for tuning |
| Staffing | Sized to realistic utilization (~60–95%) against the empirical line volume |

All shipped values are rounded/representative — no proprietary data.

## Quickstart

```bash
python run_demo.py               # baseline vs +2 frozen pickers
python run_demo.py --growth 20   # baseline vs +20% order volume
```

Python 3.10+, stdlib only (the MCP copilot layer needs `pip install mcp`).

**AI copilot:** register the twin with an MCP client (e.g. Claude Code) and ask questions
in plain English — the assistant composes the experiments itself:

```bash
claude mcp add warehouse_twin -s user -- python /path/to/twin_mcp_server.py
# then: "How many frozen pickers do we need if volume grows 30%?"
```

## Roadmap

- [x] v0.1 — DES core, empirical grounding, scenario overrides, two-scenario demo
- [x] **Replication** — `run_scenario(replications=N)` returns mean ± stdev across seeds
- [x] **AI copilot (v1)** — MCP server (`twin_mcp_server.py`) exposing `describe_twin`,
      `run_twin_scenario`, `compare_twin_scenarios`, and `sweep_twin_parameter`, so an AI
      assistant designs and runs experiments conversationally. First real result: sweeping
      FROZEN pickers 1→2→3 shows 2 is optimal (109→78→81 min avg cycle) — the third picker
      buys nothing because the bottleneck moves.
- [x] **Multi-day runs with order carryover** — saturation compounds: over 5 days the
      baseline FROZEN bottleneck grows a 180-order backlog and on-time falls to ~88%,
      dynamics a single-day view hides entirely
- [x] **GTP automation module + payback economics** — `evaluate_gtp_automation` simulates a
      goods-to-person zone (stations, rate, SKU coverage) with revised staffing and returns
      the business case. First findings: at current volume an oversized 2-station system is a
      9.5-year payback (19% utilized — does not pencil), while a right-sized single station
      saves 2 positions for a 3.6-year payback with service *improving*
- [x] **Waveless / order-streaming mode** — `{"release_mode": "waveless"}` releases orders
      on arrival instead of batched waves. Finding: waveless cuts avg cycle 116 -> 97 min at
      baseline, but the benefit shrinks under +20% growth (153 -> 145) — release discipline
      matters most when capacity has headroom; at saturation, capacity is the constraint
- [x] **Slotting module (ABC velocity)** — per-zone `slotting` config: A-movers picked from
      prime slots run ~35% faster; `prime_coverage` is the re-slotting knob (blended rate is
      anchored at calibration coverage, so gains are relative to today). Finding: re-slotting
      FROZEN 0.5 -> 0.85 halves its end-of-day queue and cuts cycle ~9 min for zero headcount —
      but at 92% utilization it delays the extra hire rather than replacing it
- [ ] Browser dashboard with live scenario comparison

## Author

Joshua Ross — ERP & WMS systems analyst (SAP Business One, Körber/Infios HighJump/KCloud),
B.S.E. Industrial Engineering. See also
[claude-ops-toolkit](https://github.com/joshuaross1014-byte/claude-ops-toolkit) — AI-assisted
monitoring and diagnostics for the same class of operation.
