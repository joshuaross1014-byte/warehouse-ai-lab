# monitors

Standalone Python monitors that run under **Windows Task Scheduler** (always-on,
independent of any editor). Each reuses a `../connectors` helper, runs a read-only
exception check, stays **silent when clean**, and posts a **Slack** alert (plus
logging) only when something trips. Exit code: `0`=clean, `1`=alert.

## Scripts

| Script | Checks | Source | Suggested schedule |
|---|---|---|---|
| `monitor_wms_import_errors.py` | real (non-benign) order-import errors + imports stuck 'I' >15m | WMS | hourly, 24/7 |
| `monitor_wave_health.py` | allocating waves stuck >2h; serial-completeness mismatches | WMS | hourly, ops hours |
| `monitor_so_price_gap.py` | regional price-list propagation gap per region; day-over-day delta | ERP (B1/HANA) | daily, before the import |
| `monitor_bot_health.py` | bot failure-rate breaches, stuck runs, scheduled-but-silent | RPA | daily |

Shared: `monitor_common.py` (UTF-8 stdout, connectors import, Slack poster, logging).
Runtime logs land in `logs/` (git-ignored).

## Setup

1. Set the connection vars in `../connectors/.env` (copy `../connectors/.env.example`).
2. Configure alerting in `monitors/.env` (copy `.env.example`): a Slack bot token
   + channel id (preferred) or an Incoming Webhook URL. Until set, alerts are
   logged + printed (dry-run), not sent.
3. Adjust site parameters: `REGIONS` in `monitor_so_price_gap.py`; thresholds in
   `.env`.
4. Register the scheduled tasks:
   ```powershell
   powershell -ExecutionPolicy Bypass -File register_tasks.ps1 -Python "C:\path\to\python.exe"
   ```

## Manage the tasks (PowerShell)

```powershell
Get-ScheduledTask     -TaskName "OpsMonitor-*"                    # list
Start-ScheduledTask   -TaskName "OpsMonitor-Bot-Health"           # run now
Get-ScheduledTaskInfo -TaskName "OpsMonitor-Bot-Health"           # last result
Unregister-ScheduledTask -TaskName "OpsMonitor-*" -Confirm:$false # remove all
```

## Notes

- Tasks run **as the logged-on user, only when logged on** (they need cached
  DB/API creds). The machine must be on. To run while logged off, re-register
  with stored credentials.
- Windows-native recurring schedules have no expiry.
- Every check is read-only; no writes without explicit human action.
