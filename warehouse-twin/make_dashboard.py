"""Generate the warehouse-twin browser dashboard (self-contained HTML).

Runs a standard scenario set through the engine (replicated), embeds the
results, and renders an offline, dependency-free dashboard:

    python make_dashboard.py            # -> docs/dashboard.html
    python make_dashboard.py --reps 20  # more replications

Charts are plain HTML/CSS (no CDN, no frameworks) with light/dark modes and
per-mark tooltips. Palette: validated reference instance (see repo README).
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

from twin import load_params, run_scenario

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCENARIOS = [
    ("Baseline",        {}),
    ("+20% volume",     {"orders_per_day": 576}),
    ("+1 FROZEN picker", {"zones.FROZEN.pickers": 2}),
    ("Waveless release", {"release_mode": "waveless"}),
]


def collect(params_path: str, reps: int) -> dict:
    p = load_params(params_path)
    scen = []
    for label, ov in SCENARIOS:
        r = run_scenario(p, ov or None, replications=reps)
        scen.append({
            "label": label,
            "on_time": r["on_time_pct"], "cycle": r["cycle_avg_min"],
            "backlog": r["backlog_at_horizon"], "completion": r["completion_pct"],
            "zones": {z: {"util": zz["utilization_pct"], "queue": zz["queue_remaining"]}
                      for z, zz in r["zones"].items()},
        })
    return {
        "site": p.site_name,
        "generated": datetime.date.today().isoformat(),
        "reps": reps,
        "orders_per_day": p.orders_per_day,
        "arrival": [round(w * 100, 1) for w in p.arrival_weights_by_hour],
        "zone_names": list(p.zones.keys()),
        "scenarios": scen,
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>warehouse-twin dashboard</title>
<style>
:root{
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --baseline:#c3c2b7; --border:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300; --seq:#2a78d6;
}
@media (prefers-color-scheme: dark){:root{
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#199e70; --s3:#c98500; --s4:#008300; --seq:#3987e5;
}}
*{box-sizing:border-box;margin:0}
body{background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px}
.wrap{max-width:1060px;margin:0 auto}
h1{font-size:20px;font-weight:650} .sub{color:var(--ink2);margin:4px 0 20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin-bottom:16px}
.card h2{font-size:13px;font-weight:600;color:var(--ink2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px}
.tile .v{font-size:28px;font-weight:650} .tile .l{color:var(--ink2);font-size:12.5px;margin-top:2px}
.tile .d{color:var(--muted);font-size:12px}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.legend span{display:inline-flex;align-items:center;gap:6px;color:var(--ink2);font-size:12.5px}
.sw{width:10px;height:10px;border-radius:3px;display:inline-block}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
.panel h3{font-size:12.5px;font-weight:600;color:var(--ink2);margin-bottom:8px}
.row{display:grid;grid-template-columns:110px 1fr 58px;align-items:center;gap:8px;height:26px}
.row .lab{color:var(--ink2);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track{position:relative;height:14px;background:transparent;border-left:2px solid var(--baseline)}
.bar{position:absolute;left:0;top:0;height:14px;border-radius:0 4px 4px 0;min-width:2px;cursor:default}
.row .val{font-size:12px;color:var(--ink2);font-variant-numeric:tabular-nums;text-align:right}
.hours{display:flex;align-items:flex-end;gap:2px;height:140px;border-bottom:2px solid var(--baseline);padding-bottom:0}
.hr{flex:1;background:var(--seq);border-radius:4px 4px 0 0;min-height:2px;cursor:default}
.hlabels{display:flex;gap:2px;margin-top:4px}
.hlabels span{flex:1;text-align:center;font-size:10px;color:var(--muted)}
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:20px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);padding:5px 9px;border-radius:6px;font-size:12px;display:none;z-index:9;max-width:260px}
.note{color:var(--muted);font-size:12px;margin-top:10px}
</style></head><body><div class="wrap">
<h1>warehouse-twin — scenario dashboard</h1>
<div class="sub" id="sub"></div>
<div class="card"><h2>Baseline at a glance</h2><div class="tiles" id="tiles"></div></div>
<div class="card"><h2>Order arrivals by hour (empirical curve, % of daily orders)</h2>
  <div class="hours" id="hours"></div><div class="hlabels" id="hlabels"></div></div>
<div class="card"><h2>Scenario comparison — mean of replicated runs</h2>
  <div class="legend" id="legend"></div><div class="panels" id="panels"></div>
  <div class="note">Bars show replication means; hover any mark for mean ± stdev. One measure per panel.</div></div>
<div class="card"><h2>Zone utilization by scenario (%)</h2><div class="groups" id="zones"></div></div>
<div class="card"><h2>All numbers (mean ± stdev)</h2><div style="overflow-x:auto"><table id="tbl"></table></div></div>
</div>
<div id="tip"></div>
<script>
const D = __DATA__;
const COLORS = ["var(--s1)","var(--s2)","var(--s3)","var(--s4)"];
const tip = document.getElementById('tip');
function showTip(e, html){ tip.innerHTML = html; tip.style.display='block';
  tip.style.left = Math.min(e.clientX+12, innerWidth-270)+'px'; tip.style.top = (e.clientY+12)+'px'; }
function hideTip(){ tip.style.display='none'; }
function hover(el, html){ el.addEventListener('mousemove', e=>showTip(e, html)); el.addEventListener('mouseleave', hideTip); }
const ms = x => x ? `${x.mean}` : '—';
const pm = x => x ? `${x.mean} ± ${x.stdev}` : '—';

document.getElementById('sub').textContent =
  `${D.site} · ${D.orders_per_day} orders/day baseline · ${D.reps} replications per scenario · generated ${D.generated}`;

// stat tiles (baseline)
const b = D.scenarios[0];
document.getElementById('tiles').innerHTML = [
  [b.on_time.mean+'%','On-time by ship cutoff','± '+b.on_time.stdev],
  [b.cycle.mean+' min','Avg cycle, arrival → complete','± '+b.cycle.stdev],
  [b.completion.mean+'%','Orders completed in horizon','± '+b.completion.stdev],
  [Math.round(b.backlog.mean),'Orders left at horizon','± '+b.backlog.stdev],
].map(t=>`<div class="tile"><div class="v">${t[0]}</div><div class="l">${t[1]}</div><div class="d">${t[2]}</div></div>`).join('');

// arrival curve — single series, sequential hue, no legend
const hmax = Math.max(...D.arrival);
const hours = document.getElementById('hours');
D.arrival.forEach((v,h)=>{ const el = document.createElement('div'); el.className='hr';
  el.style.height = (v/hmax*100)+'%'; hover(el, `${String(h).padStart(2,'0')}:00 — ${v}% of daily orders`);
  hours.appendChild(el); });
document.getElementById('hlabels').innerHTML =
  Array.from({length:24},(_,h)=>`<span>${h%6===0?h:''}</span>`).join('');

// legend (scenario identity — fixed categorical order)
document.getElementById('legend').innerHTML = D.scenarios.map((s,i)=>
  `<span><span class="sw" style="background:${COLORS[i]}"></span>${s.label}</span>`).join('');

// small-multiple KPI panels — one measure per panel, one axis each
const PANELS = [
  ['On-time %', s=>s.on_time, '%'], ['Avg cycle (min)', s=>s.cycle, ' min'],
  ['Backlog at horizon (orders)', s=>s.backlog, ''],
];
document.getElementById('panels').innerHTML = PANELS.map(p=>`<div class="panel"><h3>${p[0]}</h3>
  <div class="rows">${D.scenarios.map((s,i)=>`<div class="row"><div class="lab">${s.label}</div>
  <div class="track"><div class="bar" data-i="${i}" data-p="${p[0]}"></div></div>
  <div class="val"></div></div>`).join('')}</div></div>`).join('');
PANELS.forEach(p=>{
  const vals = D.scenarios.map(s=>p[1](s).mean); const max = Math.max(...vals)*1.08 || 1;
  document.querySelectorAll(`.bar[data-p="${p[0]}"]`).forEach(bar=>{
    const i = +bar.dataset.i, m = p[1](D.scenarios[i]);
    bar.style.width = (m.mean/max*100)+'%'; bar.style.background = COLORS[i];
    bar.closest('.row').querySelector('.val').textContent = m.mean + p[2].trim().replace('min','');
    hover(bar, `<b>${D.scenarios[i].label}</b><br>${p[0]}: ${pm(m)}${p[2]}`);
  });
});

// zone utilization — grouped bars, color follows scenario
document.getElementById('zones').innerHTML = D.zone_names.map(z=>`<div class="panel"><h3>${z}</h3>
  ${D.scenarios.map((s,i)=>{ const u=s.zones[z]?s.zones[z].util:null; if(!u) return '';
    return `<div class="row"><div class="lab">${s.label}</div>
      <div class="track"><div class="bar zb" data-z="${z}" data-i="${i}"></div></div>
      <div class="val">${u.mean}%</div></div>`;}).join('')}</div>`).join('');
document.querySelectorAll('.zb').forEach(bar=>{
  const z = bar.dataset.z, i = +bar.dataset.i, s = D.scenarios[i], u = s.zones[z].util;
  bar.style.width = Math.min(100, u.mean)+'%'; bar.style.background = COLORS[i];
  hover(bar, `<b>${s.label} — ${z}</b><br>utilization ${pm(u)}%<br>queue left ${pm(s.zones[z].queue)}`);
});

// table view (the accessibility fallback)
const zcols = D.zone_names.map(z=>`<th>${z} util %</th>`).join('');
document.getElementById('tbl').innerHTML =
  `<tr><th>Scenario</th><th>On-time %</th><th>Cycle avg (min)</th><th>Completion %</th><th>Backlog</th>${zcols}</tr>` +
  D.scenarios.map(s=>`<tr><td>${s.label}</td><td>${pm(s.on_time)}</td><td>${pm(s.cycle)}</td>
   <td>${pm(s.completion)}</td><td>${pm(s.backlog)}</td>` +
   D.zone_names.map(z=>`<td>${s.zones[z]?pm(s.zones[z].util):'—'}</td>`).join('') + `</tr>`).join('');
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params/representative_dc.json")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--out", default="docs/dashboard.html")
    args = ap.parse_args()

    data = collect(args.params, args.reps)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.replace("__DATA__", json.dumps(data)), encoding="utf-8")
    print(f"dashboard written: {out}  ({len(data['scenarios'])} scenarios, {args.reps} reps each)")


if __name__ == "__main__":
    main()
