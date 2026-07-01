"""RPA control-room (Automation Anywhere A360-style) REST auth helper.

Authenticates and returns a requests.Session with the bearer token attached.
All details come from environment variables (or a local .env).

Required env:
    RPA_URL       Control Room base URL (no trailing slash, no #/login fragment)
    RPA_USER      login username
    one of:
      RPA_APIKEY  API key (preferred), or
      RPA_PASS    password
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

_ENV = Path(__file__).with_name(".env")


def _load_env() -> None:
    if not _ENV.exists():
        return
    for raw in _ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


def _config() -> dict:
    _load_env()
    url = (os.environ.get("RPA_URL") or "").strip().rstrip("/").split("/#")[0].rstrip("/")
    if not url:
        raise RuntimeError("RPA_URL is not set")
    return {
        "url": url,
        "user": os.environ.get("RPA_USER", "").strip(),
        "apikey": os.environ.get("RPA_APIKEY", "").strip(),
        "password": os.environ.get("RPA_PASS", "").strip(),
    }


def authenticate(timeout: int = 30) -> dict:
    cfg = _config()
    if not cfg["user"]:
        raise RuntimeError("RPA_USER is not set")
    body = {"username": cfg["user"]}
    if cfg["apikey"]:
        body["apiKey"] = cfg["apikey"]
    elif cfg["password"]:
        body["password"] = cfg["password"]
    else:
        raise RuntimeError("Neither RPA_APIKEY nor RPA_PASS is set")

    # Cloud serves /v2/authentication; some on-prem builds use /v1. Try v2 first.
    last = None
    for path in ("/v2/authentication", "/v1/authentication"):
        resp = requests.post(f"{cfg['url']}{path}", json=body,
                             headers={"Content-Type": "application/json"}, timeout=timeout)
        if resp.status_code == 404:
            last = resp
            continue
        resp.raise_for_status()
        return resp.json()
    last.raise_for_status()
    return last.json()


def get_session() -> tuple[requests.Session, str]:
    """Return (session, base_url) with the bearer token pre-attached."""
    cfg = _config()
    token = authenticate().get("token")
    if not token:
        raise RuntimeError("No token in auth response")
    s = requests.Session()
    s.headers.update({"X-Authorization": token, "Content-Type": "application/json"})
    return s, cfg["url"]


if __name__ == "__main__":
    data = authenticate()
    print("Authenticated. token len:", len(data.get("token", "")))
