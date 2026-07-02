"""Simulation parameters: load, validate, and override.

Parameters live in a JSON file (see params/representative_dc.json) so scenarios
are data, not code. `SimParams.with_overrides()` applies dotted-path overrides —
the primitive the AI copilot layer uses to run what-if experiments, e.g.:

    p2 = p.with_overrides({"zones.FROZEN.pickers": 4, "orders_per_day": 312})
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ZoneParams:
    share: float          # fraction of order lines routed to this zone
    pickers: int          # picker headcount during the pick shift
    pick_rate_lph: float  # sustained lines per picker-hour


@dataclass
class SimParams:
    site_name: str
    orders_per_day: int
    lines_per_order: dict          # {distribution, mean, sigma, min, max}
    arrival_weights_by_hour: list  # 24 floats, normalized internally
    zones: dict[str, ZoneParams]
    release_mode: str              # "wave" (batch on a cadence) | "waveless" (release on arrival)
    wave_interval_min: int
    pick_shift_start_hr: int
    pick_shift_end_hr: int
    order_cutoff_hr: int           # orders arriving before this...
    ship_cutoff_hr: int            # ...should complete by this (same day)
    sim_days: int                  # consecutive days simulated; work carries over
    automation: dict               # optional GTP zone: enabled/stations/rate_lph/line_coverage
    random_seed: int
    raw: dict = field(repr=False, default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "SimParams":
        weights = d["arrival_weights_by_hour"]
        if len(weights) != 24:
            raise ValueError("arrival_weights_by_hour must have 24 entries")
        total = sum(weights)
        zones = {name: ZoneParams(**z) for name, z in d["zones"].items()}
        share_sum = sum(z.share for z in zones.values())
        if abs(share_sum - 1.0) > 0.01:
            raise ValueError(f"zone shares must sum to 1.0 (got {share_sum})")
        return cls(
            site_name=d["site_name"],
            orders_per_day=int(d["orders_per_day"]),
            lines_per_order=d["lines_per_order"],
            arrival_weights_by_hour=[w / total for w in weights],
            zones=zones,
            release_mode=d.get("release_mode", "wave"),
            wave_interval_min=int(d["wave_interval_min"]),
            pick_shift_start_hr=int(d["pick_shift"]["start_hr"]),
            pick_shift_end_hr=int(d["pick_shift"]["end_hr"]),
            order_cutoff_hr=int(d["order_cutoff_hr"]),
            ship_cutoff_hr=int(d["ship_cutoff_hr"]),
            sim_days=int(d.get("sim_days", 1)),
            automation=d.get("automation") or {"enabled": False},
            random_seed=int(d.get("random_seed", 42)),
            raw=d,
        )

    def with_overrides(self, overrides: dict[str, Any]) -> "SimParams":
        """Return a new SimParams with dotted-path overrides applied to the raw
        dict, e.g. {"zones.FROZEN.pickers": 4, "orders_per_day": 300}."""
        d = copy.deepcopy(self.raw)
        for path, value in overrides.items():
            node = d
            parts = path.split(".")
            for key in parts[:-1]:
                node = node[key]
            if parts[-1] not in node:
                raise KeyError(f"unknown parameter: {path}")
            node[parts[-1]] = value
        return SimParams.from_dict(d)


def load_params(path: str | Path) -> SimParams:
    with open(path, encoding="utf-8") as f:
        return SimParams.from_dict(json.load(f))
