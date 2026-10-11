"""Helpers shared by the blueprints: argument parsing + uniform error JSON."""
from __future__ import annotations

from functools import wraps

from flask import jsonify, request

import config
import guard


def profile() -> str:
    return config.get_profile(request.args.get("profile")).name


def arg(name: str, default: str = "") -> str:
    return (request.args.get(name) or default).strip()


def int_arg(name: str, default: int, lo: int = 1, hi: int = 100000) -> int:
    try:
        return max(lo, min(hi, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


def like(value: str) -> str:
    """User text -> LIKE pattern. Adds %...% unless the user typed a % themselves.
    Underscore is NOT treated as a user wildcard: every WMS name has one."""
    v = value.strip()
    if not v:
        return "%"
    return v if "%" in v else f"%{v}%"


def jsonerr(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except guard.GuardError as e:
            return jsonify({"error": str(e), "kind": "guard"}), 403
        except KeyError as e:
            return jsonify({"error": str(e), "kind": "bad_request"}), 400
        except Exception as e:  # noqa: BLE001 - surface SQL errors to the UI verbatim
            return jsonify({"error": str(e).splitlines()[0][:600], "kind": type(e).__name__}), 500
    return wrapper
