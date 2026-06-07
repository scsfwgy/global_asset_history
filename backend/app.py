"""Standalone Flask app for Price Change feature."""
import json
import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from routes.price_change import price_change_bp

app = Flask(__name__, static_folder=None)
CORS(app)
logging.basicConfig(level=logging.INFO)

app.register_blueprint(price_change_bp)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Visit counter — persisted to /tmp on Vercel, local file for dev
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


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/visits")
def visits():
    with _counter_lock:
        count = _read_counter() + 1
        _write_counter(count)
    return jsonify({"count": count})


@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "price-change.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8730"))
    app.run(host=host, port=port, debug=True)
