"""
WMS Dev Workbench - Flask entry point.

    python app.py            (or run.cmd)   ->  http://127.0.0.1:8765

Layers
    static/      front end   (index.html + app.js + style.css, no build step)
    api/         back end    (Flask blueprints, one per tab)
    db.py        data access (SQLAlchemy engine per profile, guarded run_query)
    queries/     the SQL     (named blocks; edit SQL without touching Python)
    guard.py     safety      (PROD read-only, TEST opt-in writes)
"""
from __future__ import annotations

from flask import Flask, jsonify, send_from_directory

import config
import db
from api import ALL

app = Flask(__name__, static_folder="static", static_url_path="/static")
for bp in ALL:
    app.register_blueprint(bp)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    """Ping each profile; never raises, so the UI can show red/green per profile."""
    out = {"profiles": {}, "queries": len(db.load_queries())}
    for name in config.PROFILES:
        try:
            res = db.run_query(name, "SELECT @@SERVERNAME AS server_name, DB_NAME() AS db, SUSER_SNAME() AS login, GETDATE() AS now", timeout=5)
            row = dict(zip(res["columns"], res["rows"][0]))
            out["profiles"][name] = {"ok": True, **row, "ms": res["ms"]}
        except Exception as e:  # noqa: BLE001
            out["profiles"][name] = {"ok": False, "error": str(e).splitlines()[0][:300]}
    return jsonify(out)


if __name__ == "__main__":
    db.load_queries()
    print(f"WMS Dev Workbench on http://127.0.0.1:{config.PORT}  (profiles: {', '.join(config.PROFILES)})")
    app.run(host="127.0.0.1", port=config.PORT, debug=False)
