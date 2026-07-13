# claude-skills

[Claude Code](https://docs.claude.com/en/docs/claude-code) **skills** — reusable,
on-demand playbooks. Each folder holds a `SKILL.md` with YAML frontmatter (`name`,
`description`) and a body that tells the agent exactly how to run one diagnostic:
which query to run, how to interpret it, and what to recommend. Invoke as
`/<skill-name>` in Claude Code.

Install by copying a skill folder into `~/.claude/skills/` (user-level) or a
project's `.claude/skills/`.

| Skill | Purpose | Paired monitor |
|---|---|---|
| `wms-import-errors` | Triage WMS order-import failures, filtering benign lock rejections | `monitor_wms_import_errors.py` |
| `wms-empty-po` | Diagnose an empty inbound PO (item not synced) and prescribe the fix | — |
| `wms-b1-reconcile` | Surface ERP↔WMS order-flow drift (both directions) | — |
| `so-price-gap` | Find the regional price-list propagation gap behind blank-price orders | `monitor_so_price_gap.py` |
| `wave-health` | Stuck waves + serial-completeness mismatches | `monitor_wave_health.py` |
| `bot-health` | RPA bot-fleet failures / stuck / silent-scheduled | `monitor_bot_health.py` |

Shared design: **read-only**, **classify benign vs real before alarming**, and a
**Monitor mode** section so the same logic can run unattended (see `../monitors`).

> Sanitized reference versions: object names are the generic vendor-standard ones
> (SAP B1, HighJump/Accellos); site-specific endpoints, identifiers, warehouse
> codes, price-list numbers, and data have been removed. Adapt to your environment.
