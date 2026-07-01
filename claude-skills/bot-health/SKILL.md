---
name: bot-health
description: Health check for an RPA bot fleet (Automation Anywhere A360-style control room) — surfaces failed/timed-out runs, stuck IN_PROGRESS bots, per-bot run/status summary, and scheduled bots that have gone silent. Use to investigate a failing bot, a missed automation, or as a scheduled daily bot-fleet monitor.
---

# RPA Bot-Fleet Health

Reports on the bot fleet via the control-room REST API (authenticated session →
`/v3/activity/list`, paged). Read-only.

## Step 1 — Pull recent activity

Fetch the last N days of activity (dynamic date window) and aggregate per bot:
run count, scheduled-run count, last start, and a status breakdown. Also collect
individual failures and any long-running IN_PROGRESS runs.

Status vocabulary: `COMPLETED` (good), `RUN_FAILED`, `DEPLOY_FAILED` (couldn't
launch — runner/device, not bot logic), `RUN_TIMED_OUT`, `RUN_ABORTED`,
`IN_PROGRESS`, `QUEUED`. Types: `SCHEDULED` vs manual.

## Step 2 — Interpret

- Weigh failures against **total runs** — a high absolute count on a very
  high-frequency poller can be a low failure *rate*. Alert on rate, with a minimum
  run count and a minimum failure floor so one blip doesn't page.
- `DEPLOY_FAILED` points at the runner/device pool, not the bot script.
- A **scheduled-but-silent** bot (ran on a schedule earlier, nothing recently) is
  often the most important finding — an automation assumed to be running that isn't.
- A **stuck IN_PROGRESS** run ties up a runner license — flag for a manual stop.

## Step 3 — Drill into a failure (optional)

Fetch the execution detail for a failing run's id to get the error, adapting the
endpoint to the control-room API version.

## Step 4 — Report

Lead with the exception summary (which bots failed and how often, with run counts;
any silent or stuck), then the per-bot table. Call a clean fleet clean.

## Monitor mode

Run daily; alert on any scheduled-but-silent bot, any stuck run, or a bot whose
failure *rate* crosses a threshold. A handful of failures on a high-frequency
poller is not alert-worthy. Read-only reporting — do not deploy/stop/modify bots.
