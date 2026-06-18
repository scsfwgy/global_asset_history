"""Standalone Flask app for Price Change feature."""
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from routes.price_change import price_change_bp
from routes.wishes import wishes_bp
from routes.etf_market import etf_market_bp
from service.price_change.config import get_site_base_url
from service.price_change import cache_store, diagnostics

app = Flask(__name__, static_folder=None)
CORS(app)
logging.basicConfig(level=logging.INFO)

app.register_blueprint(price_change_bp)
app.register_blueprint(wishes_bp)
app.register_blueprint(etf_market_bp)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEXABLE_PATHS = {"/", "/etf-market"}
ROBOT_BLOCKED_PREFIXES = ("/api/", "/settings")


def site_url() -> str:
    return os.getenv("SITE_URL", get_site_base_url()).rstrip("/")


def serve_frontend_html(filename: str):
    html = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
    html = html.replace("__SITE_BASE_URL__", site_url())
    return Response(html, mimetype="text/html")

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


@app.after_request
def add_seo_headers(response):
    path = request.path.rstrip("/") or "/"
    # Strip language prefix to check indexability
    m = re.match(r'^/(en|zh)(/.*)?$', path)
    base_path = (m.group(2) or "/") if m else path

    if base_path in INDEXABLE_PATHS:
        response.headers.setdefault("X-Robots-Tag", "index,follow")
    elif base_path.startswith(ROBOT_BLOCKED_PREFIXES) or base_path in {"/yearly", "/backtest", "/crash", "/etf", "/etf/nasdaq100", "/etf/sp500", "/etf/global_others", "/qdii-funds", "/vix", "/knowledge", "/knowledge/how-to-buy", "/knowledge/etf-intro", "/knowledge/event-myth", "/knowledge/terms", "/wishes"}:
        response.headers.setdefault("X-Robots-Tag", "noindex,follow")
    return response


@app.route("/robots.txt")
def robots_txt():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        "Disallow: /settings",
        f"Sitemap: {site_url()}/sitemap.xml",
        "",
    ])
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    langs = [("zh", "zh-CN"), ("en", "en")]
    urls = [
        ("/", "daily", "1.0"),
        ("/etf-market", "daily", "0.8"),
    ]
    items = []
    now = datetime.now(timezone.utc).date().isoformat()
    base_url = site_url()
    for path, changefreq, priority in urls:
        # Default (x-default) URL — use zh as the canonical for the root
        items.append(
            "  <url>"
            f"<loc>{base_url}{path}</loc>"
            f"<lastmod>{now}</lastmod>"
            f"<changefreq>{changefreq}</changefreq>"
            f"<priority>{priority}</priority>"
            + "".join(
                f'<xhtml:link rel="alternate" hreflang="{hreflang}" href="{base_url}/{short}{path}"/>'
                for short, hreflang in langs
            )
            + f'<xhtml:link rel="alternate" hreflang="x-default" href="{base_url}/zh{path}"/>'
            "</url>"
        )
        # Language-specific URLs
        for short, hreflang in langs:
            items.append(
                "  <url>"
                f"<loc>{base_url}/{short}{path}</loc>"
                f"<lastmod>{now}</lastmod>"
                f"<changefreq>{changefreq}</changefreq>"
                f"<priority>{priority}</priority>"
                + "".join(
                    f'<xhtml:link rel="alternate" hreflang="{h}" href="{base_url}/{s}{path}"/>'
                    for s, h in langs
                )
                + f'<xhtml:link rel="alternate" hreflang="x-default" href="{base_url}/zh{path}"/>'
                "</url>"
            )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        ' xmlns:xhtml="http://www.w3.org/1999/xhtml">'
        + "".join(items)
        + "</urlset>"
    )
    return Response(body, mimetype="application/xml")


@app.route("/etf-market")
def etf_market():
    return serve_frontend_html("etf-market.html")


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
    return serve_frontend_html("price-change.html")


# Language-prefixed routes: /en/yearly, /zh/backtest, etc.
@app.route("/<lang>")
@app.route("/<lang>/")
def index_lang(lang):
    if lang in ("en", "zh"):
        return serve_frontend_html("price-change.html")
    return serve_frontend_html("price-change.html")


@app.route("/<lang>/<path:subpath>")
def lang_frontend(lang, subpath):
    if lang not in ("en", "zh"):
        # Not a language prefix — serve as a static file from frontend/
        full_path = lang + "/" + subpath
        if full_path in {"price-change.html", "etf-market.html"}:
            return serve_frontend_html(full_path)
        return send_from_directory(str(FRONTEND_DIR), full_path)
    if subpath == "etf-market":
        return serve_frontend_html("etf-market.html")
    return serve_frontend_html("price-change.html")


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
    return serve_frontend_html("price-change.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    if filename in {"price-change.html", "etf-market.html"}:
        return serve_frontend_html(filename)
    return send_from_directory(str(FRONTEND_DIR), filename)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8730"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug)
