"""Standalone Flask app for Price Change feature."""
import json
import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from routes.price_change import price_change_bp
from routes.wishes import wishes_bp
from routes.etf_market import etf_market_bp
from service.price_change import cache_store, diagnostics

app = Flask(__name__, static_folder=None)
CORS(app)
logging.basicConfig(level=logging.INFO)

app.register_blueprint(price_change_bp)
app.register_blueprint(wishes_bp)
app.register_blueprint(etf_market_bp)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Visit counter.
# Preferred: shared Redis INCR (atomic, cross-instance, survives cold starts).
# Fallback (no Redis configured, e.g. local dev): a local JSON file. Note the
# file fallback is per-instance and reset on serverless cold start — it is only
# reliable on a persistent single-process server.
_VISIT_KEY = "visit_count"
_COUNTER_PATH = Path("/tmp/visit_count.json") if os.path.exists("/tmp") else \
    Path(__file__).resolve().parent / "config" / "visit_count.json"
_counter_lock = threading.Lock()


def _read_counter() -> int:
    try:
        if _COUNTER_PATH.exists():
            return json.loads(_COUNTER_PATH.read_text()).get("count", 0)
    except Exception:
        pass
    return 0


def _write_counter(count: int) -> None:
    _COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _COUNTER_PATH.write_text(json.dumps({"count": count}))


@app.route("/etf-market")
def etf_market():
    return send_from_directory(str(FRONTEND_DIR), "etf-market.html")


@app.route("/yearly")
@app.route("/backtest")
@app.route("/crash")
@app.route("/etf")
@app.route("/etf/nasdaq100")
@app.route("/etf/sp500")
@app.route("/etf/global_others")
@app.route("/qdii-funds")
@app.route("/vix")
@app.route("/knowledge")
@app.route("/knowledge/how-to-buy")
@app.route("/knowledge/etf-intro")
@app.route("/knowledge/event-myth")
@app.route("/knowledge/terms")
@app.route("/wishes")
@app.route("/settings")
def serve_tab():
    return send_from_directory(str(FRONTEND_DIR), "price-change.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/diag")
def diag():
    """Live reachability of upstream data sources + Redis. Read-only; results
    are memoised for ~20s. Pass ?fresh=1 to force a fresh probe."""
    fresh = request.args.get("fresh") in ("1", "true", "yes")
    return jsonify(diagnostics.run_diagnostics(fresh=fresh))


@app.route("/api/visits")
def visits():
    # Shared Redis path — atomic, correct across instances.
    if cache_store.is_enabled():
        count = cache_store.cache_incr(_VISIT_KEY)
        if count is not None:
            return jsonify({"count": count})
        # Redis transiently unavailable — fall through to the file counter.
    with _counter_lock:
        count = _read_counter() + 1
        _write_counter(count)
    return jsonify({"count": count})


_LINK_CLICKS_PATH = Path("/tmp/link_clicks.json") if os.path.exists("/tmp") else \
    Path(__file__).resolve().parent / "config" / "link_clicks.json"
_link_clicks_lock = threading.Lock()


def _read_link_clicks() -> dict:
    try:
        if _LINK_CLICKS_PATH.exists():
            return json.loads(_LINK_CLICKS_PATH.read_text())
    except Exception:
        pass
    return {}


def _write_link_clicks(data: dict) -> None:
    _LINK_CLICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LINK_CLICKS_PATH.write_text(json.dumps(data))


@app.route("/api/link-click", methods=["POST"])
def link_click():
    """Record a click on a tracked external link.
    Body: {"name": "feishu_us_stock"}  — the link identifier.
    """
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    # Shared Redis — atomic increment
    if cache_store.is_enabled():
        key = f"link_click:{name}"
        count = cache_store.cache_incr(key)
        if count is not None:
            return jsonify({"name": name, "count": count})

    # File fallback (local dev / Redis down)
    with _link_clicks_lock:
        data = _read_link_clicks()
        data[name] = data.get(name, 0) + 1
        _write_link_clicks(data)
    return jsonify({"name": name, "count": data[name]})


@app.route("/api/link-clicks", methods=["GET"])
def link_clicks():
    """Return click counts for all tracked links."""
    # Known link names
    names = ["feishu_us_stock", "github", "xiaohongshu"]
    result = {}
    if cache_store.is_enabled():
        for name in names:
            key = f"link_click:{name}"
            val = cache_store.cache_get(key)
            try:
                result[name] = int(val) if val else 0
            except (ValueError, TypeError):
                result[name] = 0
        return jsonify(result)
    return jsonify(_read_link_clicks())


@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "price-change.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8730"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug)
