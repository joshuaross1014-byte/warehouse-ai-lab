"""Shared helpers for the ops monitors (Windows Task Scheduler).

Each monitor: runs a read-only exception check, stays SILENT when clean
(logs a heartbeat, exit 0), and posts a Slack alert + logs on exception (exit 1).

Connection helpers are imported from the sibling ../connectors package.

Slack delivery (first configured mode wins):
  1. Bot token  — MONITOR_SLACK_TOKEN (xoxb-...) + MONITOR_SLACK_CHANNEL (channel/DM id)
  2. Webhook    — MONITOR_SLACK_WEBHOOK (posts to that webhook's channel)
  3. Dry-run    — neither set: print + log only.
Config comes from monitors/.env (git-ignored).
"""
from __future__ import annotations

import os
import sys
import datetime as _dt
from pathlib import Path

# Console may be a non-UTF-8 codepage; force UTF-8 so printing unicode can't
# crash a scheduled run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# Make the sibling connectors package importable.
_CONNECTORS = Path(__file__).resolve().parent.parent / "connectors"
if str(_CONNECTORS) not in sys.path:
    sys.path.insert(0, str(_CONNECTORS))

try:
    from dotenv import load_dotenv
    load_dotenv(str(Path(__file__).with_name(".env")), override=False)
except ImportError:
    pass

import requests  # noqa: E402

_LOG_DIR = Path(__file__).with_name("logs")
_LOG_DIR.mkdir(exist_ok=True)


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def log(monitor: str, message: str) -> None:
    ts = now_utc().strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"{ts}  {message}"
    with open(_LOG_DIR / f"{monitor}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def slack_alert(monitor: str, title: str, lines: list[str]) -> bool:
    """Post an alert to Slack (or dry-run). Always logs first."""
    body = f"*{title}*\n" + "\n".join(f"• {ln}" for ln in lines)
    log(monitor, f"ALERT: {title} | " + " ; ".join(lines))

    token = (os.getenv("MONITOR_SLACK_TOKEN") or "").strip()
    channel = (os.getenv("MONITOR_SLACK_CHANNEL") or "").strip()
    webhook = (os.getenv("MONITOR_SLACK_WEBHOOK") or "").strip()

    try:
        if token and channel:
            r = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "text": body}, timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                log(monitor, f"SLACK API ERROR: {data.get('error')}")
                return False
            return True
        if webhook:
            r = requests.post(webhook, json={"text": body}, timeout=20)
            r.raise_for_status()
            return True
    except Exception as e:  # noqa: BLE001
        log(monitor, f"SLACK POST FAILED: {e!r}")
        return False

    print("\n[DRY-RUN — no Slack token/webhook set] would post:\n" + body + "\n")
    return True


def heartbeat(monitor: str, summary: str) -> None:
    """Record a clean run (no alert). Logged only; never hits Slack."""
    log(monitor, f"clean — {summary}")
