"""Standalone Flask app for Price Change feature."""
import hmac
import html
import json
import logging
import os
import re
import threading
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
ROBOT_BLOCKED_PREFIXES = ("/api/", "/settings")

KNOWLEDGE_ARTICLES = {
    "/knowledge/how-to-buy-us-stocks": {
        "legacy_paths": ["/knowledge/how-to-buy"],
        "subtab": "how-to-buy",
        "en_indexable": True,
        "published": "2026-06-15",
        "updated": "2026-07-03",
        "title": {
            "zh-CN": "如何用稳定币购买美股和ETF - GlobalAssetHistory",
            "en": "How to Buy US Stocks and ETFs with Stablecoins — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "了解通过 BIT、币安和 Bitget 等平台用 USDT、USDC 参与美股和 ETF 的方式、产品结构、适合人群与风险提示。",
            "en": "A practical guide to buying US stocks and ETFs with USDT or USDC through crypto platforms, including product structure, suitability, and risks.",
        },
        "keywords": {
            "zh-CN": "稳定币买美股,USDT买美股,USDC买美股,币安美股,Bitget Stocks,BIT美股,代币化股票,rToken,美股ETF",
            "en": "buy US stocks with stablecoins,USDT US stocks,USDC ETFs,Binance stocks,Bitget Stocks,BIT stocks,tokenized stocks,rToken,US ETFs",
        },
    },
    "/knowledge/value-investing": {
        "legacy_paths": ["/knowledge/what-is-value-investing"],
        "subtab": "value-investing",
        "en_indexable": True,
        "published": "2026-07-09",
        "updated": "2026-07-09",
        "title": {
            "zh-CN": "何为价值投资 - GlobalAssetHistory",
            "en": "What Is Value Investing — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "用科普方式理解价值投资：投资和交易的区别、好投资品的特征、长期持有的前提、回撤修复和普通投资者如何建立投资系统。",
            "en": "A plain-language guide to value investing: investing vs trading, durable asset traits, long-term holding, drawdown recovery, and building an investing system.",
        },
        "keywords": {
            "zh-CN": "价值投资,长期投资,投资和交易,好公司,安全边际,投资体系,回撤修复,普通投资者",
            "en": "value investing,long-term investing,investing vs trading,quality business,margin of safety,drawdown recovery,investment system",
        },
    },
    "/knowledge/core-etf-guide": {
        "legacy_paths": ["/knowledge/etf-intro"],
        "subtab": "etf-intro",
        "en_indexable": True,
        "published": "2026-06-15",
        "updated": "2026-07-03",
        "title": {
            "zh-CN": "核心美股ETF指南：SPY、VOO、QQQ、SMH、DRAM、EWY - GlobalAssetHistory",
            "en": "Core US ETF Guide: SPY, VOO, QQQ, SMH, DRAM, EWY — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "对比核心美股 ETF、科技与半导体 ETF、DRAM 与 EWY 的历史表现、持仓特征、热门原因和主要风险。",
            "en": "Compare core US ETFs, technology and semiconductor ETFs, plus DRAM and EWY by performance, holdings, investment use case, and key risks.",
        },
        "keywords": {
            "zh-CN": "核心ETF,美股ETF,SPY,VOO,QQQ,QQQM,VGT,XLK,SMH,SOXX,DRAM,EWY,ETF持仓,ETF配置",
            "en": "core ETFs,US ETFs,SPY,VOO,QQQ,QQQM,VGT,XLK,SMH,SOXX,DRAM,EWY,ETF holdings,ETF allocation",
        },
    },
    "/knowledge/nasdaq-etf-guide": {
        "legacy_paths": ["/knowledge/nasdaq-etf"],
        "subtab": "nasdaq-etf",
        "en_indexable": True,
        "published": "2026-07-11",
        "updated": "2026-07-11",
        "title": {
            "zh-CN": "纳指ETF指南：QQQ、QQQM、IQQ、QNDX与衍生产品 - GlobalAssetHistory",
            "en": "Nasdaq ETF Guide: QQQ, QQQM, IQQ, QNDX and Variants — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "对比 QQQ、QQQM、IQQ、QNDX 的价格、发行商、费率、规模、优缺点，并介绍 ONEQ、QQEW、QQQJ、TQQQ、QLD、QYLD 等纳指衍生 ETF。",
            "en": "Compare QQQ, QQQM, IQQ, and QNDX by price, issuer, fees, size, strengths, and drawbacks, then understand ONEQ, QQEW, QQQJ, TQQQ, QLD, and QYLD.",
        },
        "keywords": {
            "zh-CN": "纳指ETF,QQQ,QQQM,IQQ,QNDX,ONEQ,QQEW,QQQJ,TQQQ,QLD,SQQQ,QYLD,纳斯达克100ETF",
            "en": "Nasdaq ETFs,QQQ,QQQM,IQQ,QNDX,ONEQ,QQEW,QQQJ,TQQQ,QLD,SQQQ,QYLD,Nasdaq-100 ETF",
        },
    },
    "/knowledge/market-data-myths": {
        "legacy_paths": ["/knowledge/event-myth"],
        "subtab": "event-myth",
        "en_indexable": True,
        "published": "2026-06-15",
        "updated": "2026-07-03",
        "title": {
            "zh-CN": "美股数据魔咒统计：世界杯、选举、总统周期和奥运会 - GlobalAssetHistory",
            "en": "Market Data Myths: World Cup, Elections, Presidential Cycle, Olympics — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "用历史数据检验世界杯、美国中期选举、总统四年周期、奥运会等市场魔咒，区分统计现象与交易信号。",
            "en": "Use historical market data to test popular market myths around the World Cup, US elections, presidential cycles, and the Olympics.",
        },
        "keywords": {
            "zh-CN": "美股数据魔咒,世界杯魔咒,中期选举行情,总统周期,奥运会行情,历史统计,S&P 500",
            "en": "market data myths,World Cup stock market,midterm elections market,presidential cycle,Olympics market,S&P 500 history",
        },
    },
    "/knowledge/financial-terms": {
        "legacy_paths": ["/knowledge/terms"],
        "subtab": "terms",
        "en_indexable": True,
        "published": "2026-06-15",
        "updated": "2026-07-03",
        "title": {
            "zh-CN": "美股、A股ETF和基金专业术语表 - GlobalAssetHistory",
            "en": "US Stock and ETF Glossary — GlobalAssetHistory",
        },
        "description": {
            "zh-CN": "整理 LOF、ETF、A类/C类、场内场外、折溢价、溢价率、跟踪误差、指数、费率、持仓、回撤和波动率等术语，方便快速查阅。",
            "en": "A glossary for US stocks, ETFs, indexes, fees, holdings, premiums, drawdowns, volatility, and market data terms.",
        },
        "keywords": {
            "zh-CN": "美股术语,A股ETF术语,LOF,ETF,A类基金,C类基金,场内基金,场外基金,溢价率,跟踪误差,指数基金,管理费,持仓,最大回撤,波动率,金融术语",
            "en": "US stock glossary,ETF glossary,index funds,expense ratio,holdings,premium,drawdown,volatility,financial terms",
        },
    },
}
KNOWLEDGE_LEGACY_PATHS = {
    legacy: path
    for path, meta in KNOWLEDGE_ARTICLES.items()
    for legacy in meta.get("legacy_paths", [])
}
INDEXABLE_PATHS = {"/", "/etf-market", "/knowledge", *KNOWLEDGE_ARTICLES.keys()}

# Real last-modified dates per page group. Update these ONLY when the page's
# HTML/content actually changes — Google discounts <lastmod> if it always shows
# "today". Knowledge articles use the per-article "updated" field instead.
INDEX_LASTMOD = "2026-07-13"
ETF_MARKET_LASTMOD = "2026-07-08"


def site_url() -> str:
    return os.getenv("SITE_URL", get_site_base_url()).rstrip("/")


def request_lang() -> str:
    m = re.match(r"^/(en|zh)(?:/|$)", request.path)
    return "en" if m and m.group(1) == "en" else "zh-CN"


def _load_locale(lang: str) -> dict:
    locale_file = "en.json" if lang == "en" else "zh-CN.json"
    try:
        return json.loads((FRONTEND_DIR / "locales" / locale_file).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _locale_value(locale: dict, key: str, fallback: str = "") -> str:
    val = locale
    for part in key.split("."):
        if not isinstance(val, dict):
            return fallback
        val = val.get(part)
    return val if isinstance(val, str) else fallback


def _json_script_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _replace_meta_content(html: str, selector: str, value: str) -> str:
    pattern = rf'(<meta\s+{selector}\s+content=")[^"]*(")'
    return re.sub(pattern, rf'\g<1>{value}\2', html, count=1)


def _base_request_path() -> str:
    path = request.path.rstrip("/") or "/"
    m = re.match(r"^/(en|zh)(/.*)?$", path)
    return (m.group(2) or "/") if m else path


def _canonical_content_path(base_path: str, filename: str) -> str:
    if filename == "etf-market.html":
        return "/etf-market"
    if base_path == "/knowledge":
        return "/knowledge/how-to-buy-us-stocks"
    if base_path in KNOWLEDGE_LEGACY_PATHS:
        return KNOWLEDGE_LEGACY_PATHS[base_path]
    if base_path in KNOWLEDGE_ARTICLES:
        return base_path
    return "/"


def _replace_json_ld(html: str, data: dict) -> str:
    script = (
        '<script type="application/ld+json">\n'
        + json.dumps(data, ensure_ascii=False, indent=2)
        + "\n    </script>"
    )
    return re.sub(
        r'<script type="application/ld\+json">.*?</script>',
        lambda _: script,
        html,
        count=1,
        flags=re.S,
    )


def _is_indexable_content_path(page_path: str, lang: str) -> bool:
    if page_path not in INDEXABLE_PATHS:
        return False
    if page_path in KNOWLEDGE_ARTICLES and lang == "en":
        return bool(KNOWLEDGE_ARTICLES[page_path].get("en_indexable"))
    return True


def serve_frontend_html(filename: str):
    lang = request_lang()
    locale = _load_locale(lang)
    base_url = site_url()
    html_lang = "en" if lang == "en" else "zh-CN"
    og_locale = "en_US" if lang == "en" else "zh_CN"
    prefix = "/en" if lang == "en" else "/zh"
    base_request_path = _base_request_path()
    page_path = _canonical_content_path(base_request_path, filename)
    page_url = f"{base_url}{prefix}{page_path}"

    html = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
    html = html.replace("__SITE_BASE_URL__", base_url)
    html = re.sub(r'<html lang="[^"]*"', f'<html lang="{html_lang}"', html, count=1)
    html = html.replace('window.__GAH_SITE_BASE_URL__ = "' + base_url + '";',
                        'window.__GAH_SITE_BASE_URL__ = "' + base_url + '";\n'
                        f'      window.__GAH_INITIAL_LANG__ = "{lang}";')

    if filename == "etf-market.html":
        title = _locale_value(locale, "seo.etfMarketTitle", _locale_value(locale, "seo.etfTitle", "GlobalAssetHistory"))
        desc = _locale_value(locale, "seo.etfMarketDescription", _locale_value(locale, "seo.etfDescription", ""))
        keywords = _locale_value(locale, "seo.etfMarketKeywords", "")
        image_url = f"{base_url}/doc/screenshot/yearly-chart.png"
        og_type = "website"
    elif page_path in KNOWLEDGE_ARTICLES:
        article = KNOWLEDGE_ARTICLES[page_path]
        title = article["title"][lang]
        desc = article["description"][lang]
        keywords = article["keywords"][lang]
        image_url = f"{base_url}/doc/screenshot/yearly-heatmap.png"
        og_type = "article"
    elif page_path == "/detail":
        title = _locale_value(locale, "seo.detailTitle", "GlobalAssetHistory")
        desc = _locale_value(locale, "seo.detailDescription", "")
        keywords = _locale_value(locale, "seo.indexKeywords", "")
        image_url = f"{base_url}/doc/screenshot/yearly-heatmap.png"
        og_type = "website"
    else:
        title = _locale_value(locale, "seo.indexTitle", "GlobalAssetHistory")
        desc = _locale_value(locale, "seo.indexDescription", "")
        keywords = _locale_value(locale, "seo.indexKeywords", "")
        image_url = f"{base_url}/doc/screenshot/yearly-heatmap.png"
        og_type = "website"

    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)
    html = _replace_meta_content(html, r'name="description"', desc)
    if keywords:
        html = _replace_meta_content(html, r'name="keywords"', keywords)
    robots_content = "index,follow" if _is_indexable_content_path(page_path, lang) and base_request_path not in KNOWLEDGE_LEGACY_PATHS else "noindex,follow"
    html = _replace_meta_content(html, r'name="robots"', robots_content)
    html = _replace_meta_content(html, r'property="og:type"', og_type)
    html = _replace_meta_content(html, r'property="og:title"', title)
    html = _replace_meta_content(html, r'property="og:description"', desc)
    html = _replace_meta_content(html, r'property="og:url"', page_url)
    html = _replace_meta_content(html, r'property="og:image"', image_url)
    html = _replace_meta_content(html, r'property="og:locale"', og_locale)
    html = _replace_meta_content(html, r'name="twitter:title"', title)
    html = _replace_meta_content(html, r'name="twitter:description"', desc)
    html = _replace_meta_content(html, r'name="twitter:image"', image_url)
    html = re.sub(r'(<link rel="canonical" href=")[^"]*(")', rf'\g<1>{page_url}\2', html, count=1)
    html = re.sub(r'(<link rel="alternate" hreflang="zh-CN" href=")[^"]*(")', rf'\g<1>{base_url}/zh{page_path}\2', html, count=1)
    html = re.sub(r'(<link rel="alternate" hreflang="en" href=")[^"]*(")', rf'\g<1>{base_url}/en{page_path}\2', html, count=1)
    html = re.sub(r'(<link rel="alternate" hreflang="x-default" href=")[^"]*(")', rf'\g<1>{base_url}/zh{page_path}\2', html, count=1)

    if page_path in KNOWLEDGE_ARTICLES:
        article = KNOWLEDGE_ARTICLES[page_path]
        html = _replace_json_ld(html, {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": desc,
            "url": page_url,
            "image": image_url,
            "author": {
                "@type": "Organization",
                "name": "GlobalAssetHistory",
            },
            "publisher": {
                "@type": "Organization",
                "name": "GlobalAssetHistory",
            },
            "mainEntityOfPage": page_url,
            "inLanguage": html_lang,
            "datePublished": article.get("published", INDEX_LASTMOD),
            "dateModified": article.get("updated", INDEX_LASTMOD),
            "articleSection": "Knowledge Base",
            "keywords": article["keywords"][lang],
        })
    elif filename == "etf-market.html":
        html = re.sub(r'("name":\s*)"[^"]*"', rf'\1{_json_script_value(title)}', html, count=1)
        html = re.sub(r'("url":\s*)"[^"]*/etf-market"', rf'\1{_json_script_value(page_url)}', html, count=1)
        html = re.sub(r'("description":\s*)"[^"]*"', rf'\1{_json_script_value(desc)}', html, count=1)
    else:
        html = re.sub(r'("url":\s*)"[^"]*/"', rf'\1{_json_script_value(page_url)}', html, count=1)
        html = re.sub(r'("description":\s*)"[^"]*"', rf'\1{_json_script_value(desc)}', html, count=1)

    return Response(html, mimetype="text/html")

# ─── Visit counter ───────────────────────────────────────────────────────────
# Preferred: shared Redis INCR (atomic, cross-instance, survives cold starts).
# Fallback (no Redis configured, e.g. local dev): a local JSON file. Note the
# file fallback is per-instance and reset on serverless cold start — it is only
# reliable on a persistent single-process server.
_VISIT_KEY = "visit_count"
_TAB_VISITS_KEY = "tab_visits"       # Redis hash: {tab_id: count}
_AD_CLICKS_KEY = "ad_clicks"         # Redis hash: {link_name: count}
_SETTINGS_CLICKS_KEY = "settings_clicks"       # Redis string: settings panel opens
_SETTINGS_ACTIONS_KEY = "settings_actions"     # Redis hash: {action: count}
# Legacy external links in the settings menu. Tracked by /api/link-click as
# separate `link_click:<name>` string keys (NOT in the ad_clicks hash), so the
# stats dashboard must read them explicitly and merge into the ad table.
_TRACKED_LINK_NAMES = ["feishu_us_stock", "github", "xiaohongshu", "tools24"]
# In-menu toggle actions (theme / color scheme / language) tracked via
# settings_action events into the settings_actions hash.
_VALID_SETTINGS_ACTIONS = {"theme", "colorscheme", "language"}

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


def _check_admin_token() -> bool:
    """Verify admin token from ?token= query param. Uses WISH_ADMIN_TOKEN env var."""
    token = request.args.get("token", "")
    admin = os.getenv("WISH_ADMIN_TOKEN", "")
    if not admin or not token:
        return False
    return hmac.compare_digest(token, admin)


@app.after_request
def add_seo_headers(response):
    base_path = _base_request_path()

    lang = request_lang()
    if base_path in INDEXABLE_PATHS and _is_indexable_content_path(base_path, lang):
        response.headers.setdefault("X-Robots-Tag", "index,follow")
    elif base_path in INDEXABLE_PATHS:
        response.headers.setdefault("X-Robots-Tag", "noindex,follow")
    elif base_path.startswith(ROBOT_BLOCKED_PREFIXES) or base_path in {"/yearly", "/detail", "/backtest", "/crash", "/etf", "/etf/nasdaq100", "/etf/sp500", "/etf/global_others", "/qdii-funds", "/vix", "/knowledge", *KNOWLEDGE_LEGACY_PATHS.keys(), "/wishes", "/heatmap"}:
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
    # (path, changefreq, priority, lastmod, include_en)
    urls = [
        ("/", "daily", "1.0", INDEX_LASTMOD, True),
        ("/etf-market", "daily", "0.8", ETF_MARKET_LASTMOD, True),
        *[(path, "weekly", "0.7", meta.get("updated", INDEX_LASTMOD), bool(meta.get("en_indexable")))
          for path, meta in KNOWLEDGE_ARTICLES.items()],
    ]
    items = []
    base_url = site_url()
    for path, changefreq, priority, lastmod, include_en in urls:
        page_langs = langs if include_en else [("zh", "zh-CN")]
        # One <url> per language variant. The default (no-lang-prefix) URL is
        # intentionally omitted: its canonical points to /zh, so listing it
        # here would create duplicates that Google flags as redundant.
        alternates = "".join(
            f'<xhtml:link rel="alternate" hreflang="{h}" href="{base_url}/{s}{path}"/>'
            for s, h in page_langs
        ) + f'<xhtml:link rel="alternate" hreflang="x-default" href="{base_url}/zh{path}"/>'
        for short, _ in page_langs:
            items.append(
                "  <url>"
                f"<loc>{base_url}/{short}{path}</loc>"
                f"<lastmod>{lastmod}</lastmod>"
                f"<changefreq>{changefreq}</changefreq>"
                f"<priority>{priority}</priority>"
                f"{alternates}"
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
@app.route("/detail")
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
@app.route("/knowledge/how-to-buy-us-stocks")
@app.route("/knowledge/value-investing")
@app.route("/knowledge/what-is-value-investing")
@app.route("/knowledge/etf-intro")
@app.route("/knowledge/core-etf-guide")
@app.route("/knowledge/nasdaq-etf")
@app.route("/knowledge/nasdaq-etf-guide")
@app.route("/knowledge/event-myth")
@app.route("/knowledge/market-data-myths")
@app.route("/knowledge/terms")
@app.route("/knowledge/financial-terms")
@app.route("/wishes")
@app.route("/settings")
@app.route("/heatmap")
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
    """Read current visit count without incrementing."""
    if cache_store.is_enabled():
        result = cache_store.cache_get(_VISIT_KEY)
        if result is not None:
            try:
                return jsonify({"count": int(result)})
            except (TypeError, ValueError):
                pass
    with _counter_lock:
        count = _read_counter()
    return jsonify({"count": count})


@app.route("/api/visits/increment", methods=["POST"])
def visits_increment():
    """Increment visit count and return new value."""
    if cache_store.is_enabled():
        count = cache_store.cache_incr(_VISIT_KEY)
        if count is not None:
            return jsonify({"count": count})
    with _counter_lock:
        count = _read_counter() + 1
        _write_counter(count)
    return jsonify({"count": count})


# ─── Event tracking ─────────────────────────────────────────────────────────
# POST /api/track  body: {"type": "tab_view", "tab": "heatmap"}
#                        {"type": "ad_click", "link": "value-investing"}
#                        {"type": "settings_click"}
_VALID_TABS = {"heatmap", "yearly", "detail", "backtest", "crash",
               "etf", "qdii-funds", "vix", "knowledge", "wishes"}


@app.route("/api/track", methods=["POST"])
def track():
    """Record a tracking event. Fire-and-forget — always returns 200."""
    body = request.get_json(silent=True) or {}
    event_type = str(body.get("type", "")).strip()

    if event_type == "tab_view":
        tab = str(body.get("tab", "")).strip()
        if tab not in _VALID_TABS:
            return jsonify({"ok": False, "error": f"unknown tab: {tab}"}), 400
        if cache_store.is_enabled():
            cache_store.cache_hincrby(_TAB_VISITS_KEY, tab)
        return jsonify({"ok": True})

    if event_type == "ad_click":
        link = str(body.get("link", "")).strip()
        if not link:
            return jsonify({"ok": False, "error": "link is required"}), 400
        if cache_store.is_enabled():
            cache_store.cache_hincrby(_AD_CLICKS_KEY, link)
        return jsonify({"ok": True})

    if event_type == "settings_click":
        if cache_store.is_enabled():
            cache_store.cache_incr(_SETTINGS_CLICKS_KEY)
        return jsonify({"ok": True})

    if event_type == "settings_action":
        action = str(body.get("action", "")).strip()
        if action not in _VALID_SETTINGS_ACTIONS:
            return jsonify({"ok": False, "error": f"unknown action: {action}"}), 400
        if cache_store.is_enabled():
            cache_store.cache_hincrby(_SETTINGS_ACTIONS_KEY, action)
        return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"unknown event type: {event_type}"}), 400


# ─── Admin stats dashboard ──────────────────────────────────────────────────
@app.route("/api/stats")
def stats_dashboard():
    """Admin-only stats dashboard. Access with ?token=<WISH_ADMIN_TOKEN>."""
    if not _check_admin_token():
        return Response(
            "<h1>401 Unauthorized</h1><p>需要 ?token= 鉴权参数</p>",
            status=401,
        )

    # Gather all stats from Redis (with file fallback for visit count + links)
    if cache_store.is_enabled():
        visit_count = cache_store.cache_get(_VISIT_KEY) or "0"
        tab_stats = cache_store.cache_hgetall(_TAB_VISITS_KEY)
        ad_stats = cache_store.cache_hgetall(_AD_CLICKS_KEY)
        settings_count = cache_store.cache_get(_SETTINGS_CLICKS_KEY) or "0"
        settings_actions = cache_store.cache_hgetall(_SETTINGS_ACTIONS_KEY)
        # Merge legacy settings-menu external links (separate string keys).
        for name in _TRACKED_LINK_NAMES:
            val = cache_store.cache_get(f"link_click:{name}")
            if val:
                ad_stats[name] = val
    else:
        with _counter_lock:
            visit_count = str(_read_counter())
        tab_stats = {}
        settings_count = "0"
        settings_actions = {}
        # Legacy external links still have a file fallback for local dev.
        with _link_clicks_lock:
            ad_stats = dict(_read_link_clicks())

    # Sort tab stats by count desc
    tab_rows = ""
    sorted_tabs = sorted(tab_stats.items(), key=lambda x: int(x[1]), reverse=True)
    tab_labels = {
        "heatmap": "热力图", "yearly": "历年涨跌幅", "detail": "涨跌详情",
        "backtest": "回测", "crash": "暴跌统计", "etf": "标普纳指ETF追踪（场内）",
        "qdii-funds": "标普纳指基金追踪（场外）", "vix": "VIX恐慌指数",
        "knowledge": "数据科普", "wishes": "心愿墙",
    }
    for rank, (tab, count) in enumerate(sorted_tabs, 1):
        label = tab_labels.get(tab, tab)
        tab_rows += f"<tr><td>{rank}</td><td>{html.escape(label)}</td><td><code>{html.escape(tab)}</code></td><td>{count}</td></tr>"

    if not sorted_tabs:
        tab_rows = '<tr><td colspan="4" style="color:#666">暂无数据</td></tr>'

    # Sort ad click stats by count desc
    ad_rows = ""
    sorted_ads = sorted(ad_stats.items(), key=lambda x: int(x[1]), reverse=True)
    ad_labels = {
        "value-investing": "何为价值投资",
        "how-to-buy": "如何投资美股",
        "feishu_us_stock": "美股投资新途径",
        "github": "Github",
        "xiaohongshu": "小红书",
        "tools24": "开发者工具",
    }
    for rank, (link, count) in enumerate(sorted_ads, 1):
        label = ad_labels.get(link, link)
        ad_rows += f"<tr><td>{rank}</td><td>{html.escape(label)}</td><td><code>{html.escape(link)}</code></td><td>{count}</td></tr>"

    if not sorted_ads:
        ad_rows = '<tr><td colspan="4" style="color:#666">暂无数据</td></tr>'

    # Settings menu toggle actions (theme / color scheme / language)
    action_rows = ""
    sorted_actions = sorted(settings_actions.items(), key=lambda x: int(x[1]), reverse=True)
    action_labels = {
        "theme": "深色/浅色模式",
        "colorscheme": "涨跌配色",
        "language": "语言切换",
    }
    for rank, (action, count) in enumerate(sorted_actions, 1):
        label = action_labels.get(action, action)
        action_rows += f"<tr><td>{rank}</td><td>{html.escape(label)}</td><td><code>{html.escape(action)}</code></td><td>{count}</td></tr>"

    if not sorted_actions:
        action_rows = '<tr><td colspan="4" style="color:#666">暂无数据</td></tr>'

    total_tab_views = sum(int(v) for v in tab_stats.values())
    total_ad_clicks = sum(int(v) for v in ad_stats.values())
    total_settings_actions = sum(int(v) for v in settings_actions.values())

    html_page = f"""<!DOCTYPE html>
<meta charset="utf-8"><title>站点统计 — GlobalAssetHistory</title>
<meta name="robots" content="noindex,nofollow">
<style>
body{{font-family:system-ui,-apple-system,Helvetica,Arial,sans-serif;max-width:900px;margin:30px auto;padding:0 20px;background:#f5f5f7;color:#1d1d1f}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}}}
h1{{font-size:1.4rem;margin-bottom:4px}}h2{{font-size:1rem;margin:28px 0 10px;color:#86868b}}
.summary{{display:flex;gap:16px;margin:16px 0;flex-wrap:wrap}}
.summary-card{{background:#fff;border-radius:12px;padding:14px 20px;min-width:130px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
@media(prefers-color-scheme:dark){{.summary-card{{background:#1a1a1a}}}}
.summary-card .num{{font-size:2rem;font-weight:700;color:#0071e3}}
.summary-card .label{{font-size:.75rem;color:#86868b;margin-top:2px}}
table{{width:100%;border-collapse:collapse;margin-bottom:8px;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
@media(prefers-color-scheme:dark){{table{{background:#1a1a1a}}}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #e5e5e5}}
@media(prefers-color-scheme:dark){{th,td{{border-color:#333}}}}
th{{color:#86868b;font-size:.75rem;font-weight:600}}
td{{font-size:.82rem}}tr:hover{{background:#f5f5f7}}
@media(prefers-color-scheme:dark){{tr:hover{{background:#222}}}}
code{{color:#0071e3;font-size:.78rem}}
.sub{{font-size:.7rem;color:#86868b}}
</style>
<h1>📊 GlobalAssetHistory 站点统计</h1>
<div class="summary">
<div class="summary-card"><div class="num">{visit_count}</div><div class="label">总访问次数</div></div>
<div class="summary-card"><div class="num">{total_tab_views}</div><div class="label">Tab 浏览</div></div>
<div class="summary-card"><div class="num">{total_ad_clicks}</div><div class="label">广告位点击</div></div>
<div class="summary-card"><div class="num">{settings_count}</div><div class="label">设置面板打开</div></div>
<div class="summary-card"><div class="num">{total_settings_actions}</div><div class="label">设置项操作</div></div>
</div>

<h2>📑 Tab 访问排行 <span class="sub">（所有用户累计）</span></h2>
<table><thead><tr><th>#</th><th>Tab</th><th>ID</th><th>次数</th></tr></thead><tbody>{tab_rows}</tbody></table>

<h2>🔗 广告位 / 外链点击排行 <span class="sub">（所有用户累计）</span></h2>
<table><thead><tr><th>#</th><th>链接</th><th>ID</th><th>次数</th></tr></thead><tbody>{ad_rows}</tbody></table>

<h2>⚙️ 设置项操作排行 <span class="sub">（所有用户累计）</span></h2>
<table><thead><tr><th>#</th><th>操作</th><th>ID</th><th>次数</th></tr></thead><tbody>{action_rows}</tbody></table>

<p class="sub" style="margin-top:24px">数据来源：Upstash Redis <code>gah:tab_visits</code> / <code>gah:ad_clicks</code> / <code>gah:settings_actions</code> / <code>gah:link_click:*</code></p>"""
    return html_page


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


_LANDING_HOSTS = {"tools24.uk", "www.tools24.uk"}


@app.route("/")
def index():
    if request.host in _LANDING_HOSTS:
        return (FRONTEND_DIR / "landing.html").read_text(encoding="utf-8")
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
