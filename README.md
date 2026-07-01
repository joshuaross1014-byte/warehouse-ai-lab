# claude-ops-toolkit

AI-assisted operations tooling for an **ERP + WMS** environment (SAP Business One
on HANA, and a HighJump/Accellos-style WMS on SQL Server), plus an RPA fleet.
Two complementary pieces:

1. **`claude-skills/`** — [Claude Code](https://docs.claude.com/en/docs/claude-code)
   skills that turn recurring diagnostics into one-command playbooks. Each encodes
   a verified investigation (query → interpret → recommend) and doubles as a
   scheduled monitor.
2. **`monitors/`** — standalone Python monitors that run under Windows Task
   Scheduler, reuse the same connection layer, stay **silent when healthy**, and
   post a Slack alert (with logging) only when a check trips.

Both share a small **`connectors/`** layer: thin, env-driven connection helpers
for the WMS (SQL Server), the ERP (SAP B1 on HANA), and the RPA control room REST
API. No credentials or endpoints live in code — everything comes from environment
variables / a local `.env` (see each `.env.example`).

## Design principles

- **Silent when clean.** Monitors alert only on genuine exceptions; healthy runs
  just log a heartbeat. Signal, not noise.
- **Read-only by default.** Every check is a SELECT / API read. No writes without
  explicit human confirmation.
- **Classify before alarming.** Each check separates benign, expected conditions
  (e.g. product-standard lock rejections, non-stockable line items) from real
  failures — the difference between an actionable alert and background noise.
- **One logic, two surfaces.** The same check runs on demand (as a Claude skill)
  and unattended (as a scheduled monitor).
- **Secrets never in git.** `.env` is git-ignored; only `.env.example` templates
  are committed.

## Layout

```
claude-ops-toolkit/
├── connectors/        env-driven connection templates (WMS / ERP / RPA) + .env.example
├── monitors/          Task Scheduler monitor scripts + shared alerting/logging
└── claude-skills/     Claude Code skills (one folder per skill, each a SKILL.md)
```

## What each monitor / skill covers

| Area | On-demand skill | Unattended monitor |
|---|---|---|
| WMS order-import failures | `wms-import-errors` | `monitor_wms_import_errors.py` |
| Empty inbound PO (item not synced) | `wms-empty-po` | — |
| ERP ↔ WMS order-flow drift | `wms-b1-reconcile` | — |
| Regional price-list propagation gap | `so-price-gap` | `monitor_so_price_gap.py` |
| WMS wave / staged-inventory health | `wave-health` | `monitor_wave_health.py` |
| RPA bot-fleet health | `bot-health` | `monitor_bot_health.py` |

## Notes

This is a sanitized, reference version: schema/object names shown are the generic
vendor-standard ones (SAP B1, HighJump/Accellos); all site-specific endpoints,
credentials, identifiers, and data have been removed. Adapt the `.env` files and
warehouse/price-list parameters to your environment.
