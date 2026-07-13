"""Discrete-event simulation engine for a grocery DC.

Zero dependencies — a heapq-driven event loop models:

  order arrivals (empirical 24h curve) -> periodic WAVE RELEASE -> zone pick
  queues (DRY / COOLER / FROZEN picker pools, exponential service times) ->
  order completion -> KPI report

The flow mirrors a real WMS: orders accumulate unreleased, a wave process
releases them to the floor on a cadence, and zone picker pools work order
lines FIFO within a pick shift. Deliberately simple v1 physics; the point is
a credible, parameterized baseline the AI copilot can run experiments against.
"""
from __future__ import annotations

import heapq
import random
import statistics
from collections import deque
from dataclasses import dataclass, field

from .params import SimParams

MIN_PER_DAY = 24 * 60


@dataclass
class Order:
    oid: int
    arrival_min: float
    lines_by_zone: dict[str, int]
    released_min: float | None = None
    done_min: float | None = None
    remaining: int = 0

    @property
    def total_lines(self) -> int:
        return sum(self.lines_by_zone.values())


@dataclass
class ZoneState:
    name: str
    pickers: int
    mean_service_min: float               # blended mean at CALIBRATION slotting
    slotting: dict | None = None          # ABC slotting config (None = uniform)
    queue: deque = field(default_factory=deque)   # one entry per line: Order ref
    idle: int = 0
    busy_min: float = 0.0
    lines_picked: int = 0
    prime_picks: int = 0
    # derived service times
    base_service_min: float = 0.0         # non-prime pick
    prime_service_min: float = 0.0        # prime-slotted pick
    prime_hit_prob: float = 0.0           # P(line is A-mover AND slotted prime)

    def __post_init__(self):
        self.idle = self.pickers
        if self.slotting:
            a = float(self.slotting["a_lines_share"])
            m = float(self.slotting["prime_rate_multiplier"])
            cov = float(self.slotting["prime_coverage"])
            cal = float(self.slotting.get("calibration_coverage", cov))
            # Anchor: the configured blended rate holds at CALIBRATION coverage,
            # so changing prime_coverage yields gains/losses relative to today
            # instead of silently recalibrating the baseline.
            f_cal = a * cal
            self.base_service_min = self.mean_service_min / (1 - f_cal + f_cal / m)
            self.prime_service_min = self.base_service_min / m
            self.prime_hit_prob = a * cov
        else:
            self.base_service_min = self.prime_service_min = self.mean_service_min


class WarehouseSim:
    def __init__(self, params: SimParams):
        self.p = params
        self.rng = random.Random(params.random_seed)
        # horizon: all simulated days + 6h spillover to let queues drain
        self.horizon_min = (params.sim_days * 24 + 6) * 60
        self.now = 0.0
        self._events: list = []
        self._seq = 0
        self.orders: list[Order] = []
        self.zones = {
            name: ZoneState(name, z.pickers, 60.0 / z.pick_rate_lph, z.slotting)
            for name, z in params.zones.items()
        }
        # optional goods-to-person zone: `line_coverage` of lines route here
        auto = params.automation
        self.gtp_coverage = 0.0
        if auto.get("enabled"):
            self.gtp_coverage = float(auto["line_coverage"])
            self.zones["GTP"] = ZoneState(
                "GTP", int(auto["stations"]), 60.0 / float(auto["rate_lph"]))
        self.unreleased: deque[Order] = deque()
        self.waves_released = 0

    # ---- event plumbing -------------------------------------------------
    def _push(self, t: float, fn, *args):
        self._seq += 1
        heapq.heappush(self._events, (t, self._seq, fn, args))

    def _in_shift(self, t: float) -> bool:
        hr = (t % MIN_PER_DAY) / 60.0
        return self.p.pick_shift_start_hr <= hr < self.p.pick_shift_end_hr

    # ---- order generation -----------------------------------------------
    def _sample_lines(self) -> int:
        lp = self.p.lines_per_order
        import math
        mu_ln = math.log(lp["mean"]) - lp["sigma"] ** 2 / 2  # mean-preserving
        n = int(round(self.rng.lognormvariate(mu_ln, lp["sigma"])))
        return max(lp["min"], min(lp["max"], n))

    def _generate_orders(self):
        zone_names = list(self.p.zones)
        zone_weights = [self.p.zones[z].share for z in zone_names]
        oid = 0
        for day in range(self.p.sim_days):
            for _ in range(self.p.orders_per_day):
                hr = self.rng.choices(range(24), weights=self.p.arrival_weights_by_hour)[0]
                arrival = day * MIN_PER_DAY + hr * 60 + self.rng.uniform(0, 60)
                lines_by_zone: dict[str, int] = {}
                for _ in range(self._sample_lines()):
                    if self.gtp_coverage and self.rng.random() < self.gtp_coverage:
                        z = "GTP"   # line's SKU is covered by the automated system
                    else:
                        z = self.rng.choices(zone_names, weights=zone_weights)[0]
                    lines_by_zone[z] = lines_by_zone.get(z, 0) + 1
                o = Order(oid, arrival, lines_by_zone)
                o.remaining = o.total_lines
                self.orders.append(o)
                self._push(arrival, self._on_arrival, o)
                oid += 1

    def _on_arrival(self, order: Order):
        if self.p.release_mode == "waveless":
            # order streaming: release straight to the floor on arrival;
            # lines queue and pickers pull them as capacity frees up
            self._release_order(order)
        else:
            self.unreleased.append(order)

    def _release_order(self, order: Order):
        order.released_min = self.now
        if order.remaining == 0:
            order.done_min = self.now
            return
        for zone_name, n in order.lines_by_zone.items():
            zq = self.zones[zone_name]
            for _ in range(n):
                zq.queue.append(order)
        for zone_name in order.lines_by_zone:
            self._dispatch(self.zones[zone_name])

    # ---- wave release ----------------------------------------------------
    def _schedule_waves(self):
        if self.p.release_mode != "wave":
            return
        horizon = self.horizon_min
        day = 0
        while day * MIN_PER_DAY < horizon:
            t = day * MIN_PER_DAY + self.p.pick_shift_start_hr * 60
            end = day * MIN_PER_DAY + self.p.pick_shift_end_hr * 60
            while t < min(end, horizon):
                self._push(t, self._on_wave)
                t += self.p.wave_interval_min
            day += 1

    def _on_wave(self):
        if not self.unreleased:
            return
        self.waves_released += 1
        while self.unreleased:
            self._release_order(self.unreleased.popleft())

    # ---- picking ----------------------------------------------------------
    def _dispatch(self, z: ZoneState):
        while z.idle > 0 and z.queue and self._in_shift(self.now):
            order = z.queue.popleft()
            z.idle -= 1
            if z.prime_hit_prob and self.rng.random() < z.prime_hit_prob:
                mean = z.prime_service_min       # A-mover picked from a prime slot
                z.prime_picks += 1
            else:
                mean = z.base_service_min
            dur = self.rng.expovariate(1.0 / mean)
            self._push(self.now + dur, self._on_line_done, z, order, dur)

    def _on_line_done(self, z: ZoneState, order: Order, dur: float):
        z.idle += 1
        z.busy_min += dur
        z.lines_picked += 1
        order.remaining -= 1
        if order.remaining == 0:
            order.done_min = self.now
        self._dispatch(z)

    def _schedule_shift_starts(self):
        """Kick idle pickers at each shift start (work left from yesterday)."""
        horizon = self.horizon_min
        day = 0
        while True:
            t = day * MIN_PER_DAY + self.p.pick_shift_start_hr * 60
            if t >= horizon:
                break
            self._push(t + 0.001, self._on_shift_start)
            day += 1

    def _on_shift_start(self):
        for z in self.zones.values():
            self._dispatch(z)

    # ---- run & report ------------------------------------------------------
    def run(self) -> dict:
        self._generate_orders()
        self._schedule_waves()
        self._schedule_shift_starts()
        horizon = self.horizon_min
        while self._events:
            t, _, fn, args = heapq.heappop(self._events)
            if t > horizon:
                break
            self.now = t
            fn(*args)
        return self._report()

    def _report(self) -> dict:
        done = [o for o in self.orders if o.done_min is not None]
        cyc_arr = [o.done_min - o.arrival_min for o in done]
        cyc_rel = [o.done_min - o.released_min for o in done if o.released_min is not None]
        # cutoffs are per-day: an order arriving before the order cutoff on day d
        # should complete by the ship cutoff of the SAME day d
        cutoff_arr = self.p.order_cutoff_hr * 60
        cutoff_ship = self.p.ship_cutoff_hr * 60
        eligible = [o for o in self.orders
                    if (o.arrival_min % MIN_PER_DAY) <= cutoff_arr]
        ontime = [o for o in eligible if o.done_min is not None
                  and o.done_min <= (o.arrival_min // MIN_PER_DAY) * MIN_PER_DAY + cutoff_ship]
        shift_min = (self.p.pick_shift_end_hr - self.p.pick_shift_start_hr) * 60 * self.p.sim_days

        def p90(xs):
            return sorted(xs)[int(0.9 * (len(xs) - 1))] if xs else None

        return {
            "site": self.p.site_name,
            "days_simulated": self.p.sim_days,
            "orders": {
                "arrived": len(self.orders),
                "completed": len(done),
                "completion_pct": round(100 * len(done) / max(1, len(self.orders)), 1),
                "backlog_at_horizon": len(self.orders) - len(done),
            },
            "lines": {
                "total": sum(o.total_lines for o in self.orders),
                "picked": sum(z.lines_picked for z in self.zones.values()),
            },
            "waves_released": self.waves_released,
            "cycle_time_min": {
                "arrival_to_complete_avg": round(statistics.mean(cyc_arr), 1) if cyc_arr else None,
                "arrival_to_complete_p90": round(p90(cyc_arr), 1) if cyc_arr else None,
                "release_to_complete_avg": round(statistics.mean(cyc_rel), 1) if cyc_rel else None,
            },
            "service_level": {
                "cutoff_eligible_orders": len(eligible),
                "shipped_by_cutoff": len(ontime),
                "on_time_pct": round(100 * len(ontime) / max(1, len(eligible)), 1),
            },
            "zones": {
                z.name: {
                    "pickers": z.pickers,
                    "lines_picked": z.lines_picked,
                    "queue_remaining": len(z.queue),
                    "utilization_pct": round(100 * z.busy_min / (z.pickers * shift_min), 1),
                    "prime_pick_pct": round(100 * z.prime_picks / max(1, z.lines_picked), 1),
                }
                for z in self.zones.values()
            },
        }


def run_scenario(params: SimParams, overrides: dict | None = None,
                 replications: int = 1) -> dict:
    """One-call API: apply overrides, run the day, return the KPI report.
    This is the function the AI copilot layer wraps as a tool.

    replications > 1 runs the same scenario under different random seeds and
    returns mean +/- stdev for the headline KPIs — variance-aware answers
    instead of single-draw anecdotes."""
    if overrides:
        params = params.with_overrides(overrides)
    if replications <= 1:
        return WarehouseSim(params).run()

    reports = []
    for i in range(replications):
        p_i = params.with_overrides({"random_seed": params.random_seed + i})
        reports.append(WarehouseSim(p_i).run())
    return _aggregate(reports)


def _aggregate(reports: list[dict]) -> dict:
    """Mean +/- stdev across replication reports (headline scalars + zones)."""
    def stat(values):
        vals = [v for v in values if v is not None]
        if not vals:
            return None
        m = statistics.mean(vals)
        s = statistics.stdev(vals) if len(vals) > 1 else 0.0
        return {"mean": round(m, 1), "stdev": round(s, 1)}

    zones = {}
    for zname in reports[0]["zones"]:
        zones[zname] = {
            "pickers": reports[0]["zones"][zname]["pickers"],
            "utilization_pct": stat([r["zones"][zname]["utilization_pct"] for r in reports]),
            "queue_remaining": stat([r["zones"][zname]["queue_remaining"] for r in reports]),
            "lines_picked": stat([r["zones"][zname]["lines_picked"] for r in reports]),
            "prime_pick_pct": stat([r["zones"][zname].get("prime_pick_pct") for r in reports]),
        }
    return {
        "site": reports[0]["site"],
        "days_simulated": reports[0].get("days_simulated", 1),
        "replications": len(reports),
        "orders_arrived": stat([r["orders"]["arrived"] for r in reports]),
        "completion_pct": stat([r["orders"]["completion_pct"] for r in reports]),
        "backlog_at_horizon": stat([r["orders"]["backlog_at_horizon"] for r in reports]),
        "on_time_pct": stat([r["service_level"]["on_time_pct"] for r in reports]),
        "cycle_avg_min": stat([r["cycle_time_min"]["arrival_to_complete_avg"] for r in reports]),
        "cycle_p90_min": stat([r["cycle_time_min"]["arrival_to_complete_p90"] for r in reports]),
        "waves_released": stat([r["waves_released"] for r in reports]),
        "zones": zones,
    }
