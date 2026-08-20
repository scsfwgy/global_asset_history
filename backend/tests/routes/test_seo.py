"""Tests for SEO configuration: sitemap.xml, robots.txt, rendered meta tags, JSON-LD.

These guard against regressions in search-engine indexing signals:
- sitemap must list only canonical (language-prefixed) URLs with real lastmod
  values taken from configured constants, not datetime.now() (Google discounts
  a sitemap whose lastmod is always "today").
- the no-lang-prefix URL variants are intentionally omitted because their
  canonical points to /zh — listing them would create duplicates.
- robots.txt must block /api/ and /settings.
- rendered HTML must carry correct canonical / robots / og:image meta.
- Article JSON-LD must include datePublished and a real dateModified.
"""

import json
import os
import re
import xml.etree.ElementTree as ET

import pytest
from service.price_change.common import PriceSeries
import app as app_module

from app import (
    ETF_MARKET_LASTMOD,
    FRONTEND_DIR,
    INDEX_LASTMOD,
    INDEXABLE_TOOL_PATHS,
    KNOWLEDGE_ARTICLES,
    app as flask_app,
)

SITE_URL = "https://test.local"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
XHTML_NS = "{http://www.w3.org/1999/xhtml}"


@pytest.fixture
def client():
    """Flask test client with a fixed SITE_URL so absolute URLs are stable."""
    os.environ["SITE_URL"] = SITE_URL
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _sitemap_urls(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/xml"
    root = ET.fromstring(resp.get_data(as_text=True))
    return root.findall(f"{SITEMAP_NS}url")


def _json_ld(client, path):
    html = client.get(path).get_data(as_text=True)
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        flags=re.DOTALL,
    )
    assert match, f"missing JSON-LD on {path}"
    return json.loads(match.group(1))


# ═══════════════════════════════════════════════════════════════════════════
# robots.txt
# ═══════════════════════════════════════════════════════════════════════════
class TestRobotsTxt:
    """GET /robots.txt"""

    def test_blocks_api_and_settings(self, client):
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "User-agent: *" in body
        assert "Allow: /" in body
        assert "Disallow: /api/" in body
        assert "Disallow: /settings" in body
        assert f"Sitemap: {SITE_URL}/sitemap.xml" in body


# ═══════════════════════════════════════════════════════════════════════════
# sitemap.xml
# ═══════════════════════════════════════════════════════════════════════════
class TestSitemap:
    """GET /sitemap.xml — structure and real lastmod."""

    def test_only_language_prefixed_locs(self, client):
        """Every <loc> must carry a /zh, /zh-TW or /en prefix — the no-prefix
        variant canonicalizes to /zh, so listing it creates a duplicate Google flags."""
        urls = _sitemap_urls(client)
        locs = [u.findtext(f"{SITEMAP_NS}loc") for u in urls]
        assert locs, "sitemap should not be empty"
        for loc in locs:
            assert (
                f"{SITE_URL}/zh-TW" in loc
                or f"{SITE_URL}/zh" in loc
                or f"{SITE_URL}/en" in loc
            ), f"no-prefix URL leaked into sitemap: {loc}"

    def test_no_duplicate_locs(self, client):
        locs = [u.findtext(f"{SITEMAP_NS}loc") for u in _sitemap_urls(client)]
        assert len(locs) == len(set(locs)), "duplicate loc in sitemap"

    def test_url_count_matches_pages_times_languages(self, client):
        # Top-level pages, indexable tools, articles and intent landing pages.
        urls = _sitemap_urls(client)
        expected = (2 + len(INDEXABLE_TOOL_PATHS) + len(KNOWLEDGE_ARTICLES)) * 3
        assert len(urls) == expected

    def test_lastmod_uses_fixed_constants(self, client):
        """lastmod must come from configured constants, not datetime.now()."""
        allowed = {
            INDEX_LASTMOD,
            ETF_MARKET_LASTMOD,
            *(m.get("updated") for m in KNOWLEDGE_ARTICLES.values()),
        }
        for u in _sitemap_urls(client):
            loc = u.findtext(f"{SITEMAP_NS}loc")
            lastmod = u.findtext(f"{SITEMAP_NS}lastmod")
            assert lastmod in allowed, f"{loc}: lastmod {lastmod!r} not a fixed constant"

    def test_home_lastmod_matches_index_constant(self, client):
        for u in _sitemap_urls(client):
            loc = u.findtext(f"{SITEMAP_NS}loc")
            if loc.endswith("/zh/") or loc.endswith("/zh-TW/") or loc.endswith("/en/"):
                assert u.findtext(f"{SITEMAP_NS}lastmod") == INDEX_LASTMOD

    def test_each_url_has_full_hreflang_set(self, client):
        for u in _sitemap_urls(client):
            hreflangs = {a.get("hreflang") for a in u.findall(f"{XHTML_NS}link")}
            assert {"zh-CN", "zh-TW", "en", "x-default"} <= hreflangs


# ═══════════════════════════════════════════════════════════════════════════
# Rendered HTML meta tags
# ═══════════════════════════════════════════════════════════════════════════
class TestHtmlMeta:
    """Canonical / robots / og:image on rendered pages."""

    def test_zh_home_canonical_points_to_self(self, client):
        html = client.get("/zh/").get_data(as_text=True)
        assert '<link rel="canonical" href="https://test.local/zh/"' in html
        assert 'name="robots" content="index,follow"' in html

    def test_en_home_canonical_points_to_self(self, client):
        html = client.get("/en/").get_data(as_text=True)
        assert '<link rel="canonical" href="https://test.local/en/"' in html

    def test_zh_tw_home_renders_traditional_head(self, client):
        html = client.get("/zh-TW/").get_data(as_text=True)
        assert '<html lang="zh-TW"' in html
        assert '<link rel="canonical" href="https://test.local/zh-TW/"' in html
        assert "GlobalAssetHistory - 歷史漲跌幅與定投回測工具" in html
        assert 'property="og:locale" content="zh_TW"' in html

    @pytest.mark.parametrize("path", ["/zh-TW/yearly", "/zh-TW/backtest", "/zh-TW/etf-market"])
    def test_zh_tw_subpath_routes_render(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '<html lang="zh-TW"' in html
        assert f'<link rel="canonical" href="https://test.local{path}"' in html

    def test_zh_tw_settings_route_is_not_404(self, client):
        resp = client.get("/zh-TW/settings")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '<html lang="zh-TW"' in html
        # Language pick list (not a cycling toggle): three selectable options.
        assert 'id="settingsLangMenu"' in html
        assert 'data-lang="zh-CN">简体中文</button>' in html
        assert 'data-lang="zh-TW">繁體中文</button>' in html
        assert 'data-lang="en">English</button>' in html

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("zh-TW,zh;q=0.9,en;q=0.8", "zh-TW"),
            ("zh-HK,zh;q=0.9", "zh-TW"),
            ("zh-Hant-TW,zh;q=0.8", "zh-TW"),
            ("en-US,en;q=0.9", "en"),
            ("zh-CN,zh;q=0.9", "zh-CN"),
            ("fr-FR,fr;q=0.9", "zh-CN"),
            ("", "zh-CN"),
        ],
    )
    def test_accept_lang_maps_to_supported_language(self, client, header, expected):
        html = client.get("/", headers={"Accept-Language": header}).get_data(as_text=True)
        assert f'<html lang="{expected}"' in html

    def test_frontend_assets_use_content_version_and_explicit_cache_policy(self, client):
        response = client.get("/zh/")
        html = response.get_data(as_text=True)
        version = response.headers["X-Frontend-Version"]
        assert len(version) == 12
        assert response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
        assert f'href="/css/app.css?v={version}"' in html
        assert f'src="/js/i18n.js?v={version}"' in html
        assert f'window.__GAH_ASSET_VERSION__ = "{version}"' in html

        unversioned = client.get("/js/i18n.js")
        assert unversioned.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
        versioned = client.get(f"/js/i18n.js?v={version}")
        assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"

    def test_crash_controls_use_unambiguous_period_and_chart_row_labels(self, client):
        html = client.get("/zh/crash").get_data(as_text=True)
        assert 'data-i18n="crash.periodType">K 线周期<' in html
        assert 'data-i18n="crash.chartDays">图表详情条数<' in html
        assert 'data-i18n="crash.detailRowsUnit">条<' in html
        assert html.index('id="crashEndDate"') < html.index('id="crashChartDays"')

    def test_frontend_version_changes_for_uncommitted_file_content(self, tmp_path, monkeypatch):
        asset = tmp_path / "app.js"
        asset.write_text("const value = 1;", encoding="utf-8")
        monkeypatch.setattr(app_module, "FRONTEND_DIR", tmp_path)
        monkeypatch.setattr(app_module, "_FRONTEND_VERSION_SIGNATURE", None)
        monkeypatch.setattr(app_module, "_FRONTEND_VERSION_VALUE", None)
        first = app_module._frontend_asset_version()

        asset.write_text("const value = 200;", encoding="utf-8")
        second = app_module._frontend_asset_version()

        assert first != second

    def test_home_og_image_path_is_hosted_path(self, client):
        html = client.get("/zh/").get_data(as_text=True)
        assert (
            'og:image" content="https://test.local/doc/screenshot/yearly-chart.png"'
            in html
        )
        assert 'property="og:image:width" content="2784"' in html
        assert 'property="og:image:height" content="1304"' in html
        assert 'property="og:image:alt"' in html

    @pytest.mark.parametrize(
        "path",
        [
            "/knowledge/how-to-buy-us-stocks",
            "/knowledge/value-investing",
            "/knowledge/nasdaq-etf-guide",
            "/knowledge/vix-vxn-investing-signal",
            "/knowledge/spy-volatility-history",
        ],
    )
    def test_knowledge_article_jsonld_dates(self, client, path):
        article = KNOWLEDGE_ARTICLES[path]
        html = client.get(f"/zh{path}").get_data(as_text=True)
        assert '"datePublished"' in html
        assert f'"dateModified": "{article["updated"]}"' in html

    def test_knowledge_legacy_alias_is_noindex_and_canonicalized(self, client):
        html = client.get("/zh/knowledge/what-is-value-investing").get_data(as_text=True)
        assert 'name="robots" content="noindex,follow"' in html
        assert '<link rel="canonical" href="https://test.local/zh/knowledge/value-investing"' in html

    def test_nasdaq_etf_article_route_and_content(self, client):
        html = client.get("/zh/knowledge/nasdaq-etf-guide").get_data(as_text=True)
        assert "QQQM" in html
        assert "QNDX" in html
        assert 'data-kb-tab="nasdaq-etf"' in html
        assert '<link rel="canonical" href="https://test.local/zh/knowledge/nasdaq-etf-guide"' in html

    def test_vix_vxn_study_route_content_and_locales(self, client):
        zh_html = client.get("/zh/knowledge/vix-vxn-investing-signal").get_data(as_text=True)
        en_html = client.get("/en/knowledge/vix-vxn-investing-signal").get_data(as_text=True)

        assert 'data-vix-view="overview"' in zh_html
        assert 'data-i18n="vix.viewOverview">数据概述</button>' in zh_html
        assert 'data-kb-tab="vix-vxn-study"' not in zh_html
        assert 'id="kb-vix-vxn-study"' in zh_html
        assert "VIX≥40 后1年" in zh_html
        assert "VXN≥50：独立事件" in zh_html
        assert "-54.2%" in zh_html
        assert 'id="kb-vix-vxn-study-en"' in en_html
        assert "One-Year Outcomes After High Readings" in en_html
        script = client.get("/js/vix-chart.js").get_data(as_text=True)
        assert 'overviewView.appendChild(panel)' in script
        assert 'cleanPath === "/knowledge/vix-vxn-investing-signal"' in script
        assert 'url.pathname = typeof __langPath === "function"' in script
        assert '<link rel="canonical" href="https://test.local/zh/knowledge/vix-vxn-investing-signal"' in zh_html
        assert '<link rel="canonical" href="https://test.local/en/knowledge/vix-vxn-investing-signal"' in en_html
        assert '"articleSection": "US Fear Index"' in zh_html

    def test_spy_volatility_history_route_content_and_locales(self, client):
        zh_html = client.get("/zh/knowledge/spy-volatility-history").get_data(as_text=True)
        en_html = client.get("/en/knowledge/spy-volatility-history").get_data(as_text=True)

        assert 'data-kb-tab="spy-volatility"' in zh_html
        assert zh_html.count("<h1") == 1
        assert ">SPY剧烈波动</h1>" in zh_html
        assert 'id="kb-spy-volatility"' in zh_html
        assert "15次重大波动期" in zh_html
        assert "-56.47%" in zh_html
        assert "44个极端交易日" in zh_html
        assert "谷底后收复" in zh_html
        assert "1,168" in zh_html
        assert "有没有不是先暴跌" in zh_html
        assert "2000-01-07" in zh_html
        assert "+34.95%" in zh_html
        assert 'id="kb-spy-volatility-en"' in en_html
        assert ">SPY Volatility</h1>" in en_html
        assert "44 extreme trading days" in en_html
        assert "Recovery<br>sessions" in en_html
        assert "Can Good News Drive a Rally Without a Prior Crash?" in en_html
        assert "January 7, 2000" in en_html
        assert '<link rel="canonical" href="https://test.local/zh/knowledge/spy-volatility-history"' in zh_html
        assert '<link rel="canonical" href="https://test.local/en/knowledge/spy-volatility-history"' in en_html

    @pytest.mark.parametrize("path", ["/yearly", "/detail", "/stock-compare", "/backtest"])
    def test_indexable_tools_have_self_canonical_and_consistent_robots(self, client, path):
        resp = client.get(f"/en{path}")
        html = resp.get_data(as_text=True)
        assert resp.headers["X-Robots-Tag"] == "index,follow"
        assert 'name="robots" content="index,follow"' in html
        assert f'<link rel="canonical" href="{SITE_URL}/en{path}"' in html

    def test_tool_navigation_uses_crawlable_language_links(self, client):
        html = client.get("/en/backtest").get_data(as_text=True)
        assert '<a href="/en/yearly" data-tab="yearly"' in html
        assert '<h1 data-tab="backtest" class="tab-btn active" aria-current="page"' in html
        assert '>Backtest</h1>' in html
        assert html.count('class="header-quick-link"') == 2
        assert '<a class="header-quick-link" href="/en/knowledge/value-investing"' in html
        assert '<a class="header-quick-link" href="/en/knowledge/how-to-buy-us-stocks"' in html
        assert "__LANG_PREFIX__" not in html

    @pytest.mark.parametrize(
        "path,active_panel,excluded_panel,required_script,excluded_script",
        [
            ("/zh/yearly", "tab-yearly", "tab-detail", "price-change.js", "price-detail.js"),
            ("/en/detail", "tab-detail", "tab-backtest", "price-detail.js", "backtest.js"),
            ("/zh/backtest", "tab-backtest", "tab-vix", "backtest.js", "vix-chart.js"),
        ],
    )
    def test_tool_routes_only_ship_the_active_panel_and_scripts(
        self,
        client,
        path,
        active_panel,
        excluded_panel,
        required_script,
        excluded_script,
    ):
        html = client.get(path).get_data(as_text=True)
        assert f'id="{active_panel}"' in html
        assert f'id="{excluded_panel}"' not in html
        assert f'/js/{required_script}' in html
        assert f'/js/{excluded_script}' not in html
        assert html.count("<h1") == 1
        assert len(html.encode("utf-8")) < 220_000

    def test_common_bundle_supplies_helpers_used_by_focused_routes(self, client):
        script = client.get("/js/api.js").get_data(as_text=True)
        assert "function normalizeAssetSymbol" in script
        assert "function escapeHtml" in script

    def test_vix_header_badge_ships_on_all_routes(self, client):
        # The VIX header badge is a site-wide decoration; its loader must ship
        # on every route, not only the VIX tab (which uses vix-chart.js).
        for path in ("/heatmap", "/yearly", "/detail"):
            html = client.get(path).get_data(as_text=True)
            assert "/js/vix-badge.js" in html
            assert "/js/vix-chart.js" not in html
        badge = client.get("/js/vix-badge.js").get_data(as_text=True)
        assert "window.VixBadge" in badge

    def test_route_documents_are_unique_and_have_specific_headings(self, client):
        yearly = client.get("/zh/yearly").get_data(as_text=True)
        detail = client.get("/zh/detail").get_data(as_text=True)
        heatmap = client.get("/zh/heatmap").get_data(as_text=True)

        assert yearly != detail != heatmap
        assert '>历年涨跌幅</h1>' in yearly
        assert '>股票详情</h1>' in detail
        assert '>热力图</h1>' in heatmap
        assert 'class="seo-page-intro"' not in yearly
        assert 'class="seo-page-intro"' not in detail
        assert 'class="seo-page-intro"' not in heatmap

    def test_article_route_only_ships_selected_language_and_article(self, client):
        html = client.get("/zh/knowledge/value-investing").get_data(as_text=True)
        assert 'id="kb-value-investing"' in html
        assert 'id="kb-value-investing-en"' not in html
        assert 'id="kb-how-to-buy"' not in html
        assert html.count("<article") == 1
        assert html.count("<h1") == 1
        assert '>何为价值投资</h1>' in html
        assert 'class="seo-page-intro' not in html
        assert 'GlobalAssetHistory 编辑团队' not in html
        assert '<time datetime="2026-08-11">' not in html
        assert 'class="seo-editorial-note"' not in html

        css = client.get("/css/app.css").get_data(as_text=True)
        assert "#tab-knowledge #kbSubTabs" in css
        assert "margin-left: 0 !important" in css

    def test_noindex_route_has_matching_header_meta_and_self_canonical(self, client):
        resp = client.get("/zh/download")
        html = resp.get_data(as_text=True)
        assert resp.headers["X-Robots-Tag"] == "noindex,follow"
        assert 'name="robots" content="noindex,follow"' in html
        assert '<link rel="canonical" href="https://test.local/zh/download"' in html
        assert '>数据下载</h1>' in html

    def test_heatmap_is_indexable_and_listed_in_sitemap(self, client):
        response = client.get("/zh/heatmap")
        html = response.get_data(as_text=True)
        assert response.headers["X-Robots-Tag"] == "index,follow"
        assert 'data-route-focused="true"' in html
        assert "dataset.routeFocused === 'true'" in html
        locs = [url.findtext(f"{SITEMAP_NS}loc") for url in _sitemap_urls(client)]
        assert f"{SITE_URL}/zh/heatmap" in locs
        assert f"{SITE_URL}/en/heatmap" in locs

    def test_affiliate_links_keep_machine_relationship_labels(self, client):
        html = client.get("/zh/knowledge/how-to-buy-us-stocks").get_data(as_text=True)
        assert '>如何购买美股</h1>' in html
        assert 'class="seo-page-intro' not in html
        assert 'class="seo-disclosure"' not in html
        assert "站点可能获得平台奖励" not in html
        assert 'rel="sponsored nofollow noopener noreferrer"' in html

        english = client.get("/en/knowledge/value-investing").get_data(as_text=True)
        assert '>Value Investing</h1>' in english
        assert '>何为价值投资</h1>' not in english

    def test_json_ld_graph_covers_entity_breadcrumb_and_public_dataset(self, client):
        graph = _json_ld(client, "/en/us-etf/qqqm")["@graph"]
        types = {node["@type"] for node in graph}
        assert {"Organization", "WebSite", "Article", "BreadcrumbList", "Dataset"} <= types
        dataset = next(node for node in graph if node["@type"] == "Dataset")
        assert dataset["distribution"]["contentUrl"] == (
            "https://test.local/datasets/qqqm-holdings.csv"
        )

    def test_yearly_data_waits_for_explicit_query(self, client):
        script = client.get("/js/price-change.js").get_data(as_text=True)
        assert "_initialYearlyFetchDone" not in script
        assert "isYearlyRoute" not in script

        preset_start = script.index("function loadPreset")
        preset_end = script.index("function renderPresetChips", preset_start)
        assert "fetchData()" not in script[preset_start:preset_end]
        assert 'refreshBtn.addEventListener("click", fetchData)' in script
        assert (
            'typeof updateBacktestFrequencyUI === "function"' in script
        )

    def test_vix_uses_candles_for_spy_qqq_and_lines_for_fear_indexes(self, client):
        script = client.get("/js/vix-chart.js").get_data(as_text=True)
        assert "normalizeCandleSeries" in script
        assert "_vixData.spy_candles" in script
        assert "_vixData.qqq_candles" in script
        assert "_vixData.vix" in script
        assert "_vixData.vxn" in script
        assert 'name: "VIX"' in script
        assert 'name: "VXN"' in script
        assert 'kind: "candle"' in script
        assert 'kind: "line"' in script
        assert 'class="vix-candle-body vix-candle-' in script
        assert 'class="vix-candle-wick vix-candle-' in script
        assert "CLR.positive" in script
        assert "CLR.negative" in script
        assert 'candleStyle = series.key === "spy" ? "solid" : "hollow"' in script
        assert "var candleX = dateX[point.date]" in script
        assert "candleOffset" not in script
        assert 'candleStyle === "solid" ? directionColor : "none"' in script
        assert 'data-style="' in script
        assert "legendHollow" in script

    def test_vix_threshold_stats_subtab_has_filters_and_result_table(self, client):
        html = client.get("/zh/vix").get_data(as_text=True)
        script = client.get("/js/vix-chart.js").get_data(as_text=True)
        api_script = client.get("/js/api.js").get_data(as_text=True)

        assert 'id="vixViewTabs"' in html
        assert 'data-vix-view="threshold"' in html
        assert 'data-vix-view="overview"' in html
        assert 'id="vixOverviewView"' in html
        assert 'id="fearStatsIndex"' in html
        assert '<option value="VIX">VIX → SPY</option>' in html
        assert '<option value="VXN">VXN → QQQ</option>' in html
        assert 'id="fearStatsThreshold"' in html
        assert 'id="fearStatsStartDate"' in html
        assert 'id="fearStatsEndDate"' in html
        assert 'id="fearStatsBody"' in html
        assert "fetchFearThresholdStats" in script
        assert "forward.half_year" in script
        assert "FEAR_THRESHOLD_STATS_ENDPOINT" in script
        assert "/api/price-change/fear-threshold-stats" in api_script

    def test_exchange_loss_tab_has_chart_and_calculator(self, client):
        html = client.get("/zh/exchange-loss").get_data(as_text=True)
        script = client.get("/js/exchange-loss.js").get_data(as_text=True)
        api_script = client.get("/js/api.js").get_data(as_text=True)

        # New tab button sits right after the VIX tab button.
        assert html.index('data-tab="vix"') < html.index('data-tab="exchange-loss"')
        assert 'data-tab="exchange-loss"' in html
        assert 'id="tab-exchange-loss"' in html
        assert '/js/exchange-loss.js' in html
        assert 'id="fxChartTitle"' in html
        assert 'id="fxChartContainer"' in html
        # K-line period tabs + count (defaults 730 / 105 / 24).
        assert 'id="fxPeriodTabs"' in html
        assert 'data-fx-period="daily"' in html
        assert 'data-fx-period="weekly"' in html
        assert 'data-fx-period="monthly"' in html
        assert 'id="fxCountInput"' in html
        assert 'value="730"' in html
        # Chart mode (line/candle), mutual-exclusive 条数/跟随 toggle, reset zoom.
        assert 'id="fxChartModeTabs"' in html
        assert 'data-fx-mode="line"' in html
        assert 'data-fx-mode="candle"' in html
        assert 'id="fxRangeModeTabs"' in html
        assert 'data-fx-range="count"' in html
        assert 'data-fx-range="follow"' in html
        assert 'id="fxResetZoom"' in html
        assert 'id="fxJumpLeftBtn"' in html
        assert 'id="fxJumpRightBtn"' in html
        # Manual load button + calculator controls.
        assert 'id="fxLoadBtn"' in html
        assert 'id="fxHeldCurrency"' in html
        assert 'id="fxAmount"' in html
        assert 'value="2025-01-01"' in html
        assert 'id="fxStartDate"' in html
        assert 'id="fxTargetCurrency"' in html
        assert 'id="fxEndDate"' in html
        assert 'id="fxCalcResults"' in html
        # Detail list: aggregation field + table + pagination.
        assert 'id="fxAggCount"' in html
        assert 'id="fxDetailBody"' in html
        assert 'id="fxDetailPagination"' in html
        assert 'id="fxDetailPrevBtn"' in html
        assert 'id="fxDetailNextBtn"' in html
        # No USDT/stablecoin leftovers, no old lookback table.
        panel_html = html[html.index('id="tab-exchange-loss"'):html.index('/tab-exchange-loss')]
        assert "USDT" not in panel_html
        assert "fxLookbackBody" not in panel_html
        assert "fetchFxData" in script
        assert "EXCHANGE_LOSS_ENDPOINT" in script
        assert "rateAt" in script
        assert "FX_CURRENCIES" in script
        assert "groupOHLC" in script
        assert "PERIOD_COUNTS" in script
        assert "buildDetailRows" in script
        assert "renderDetail" in script
        assert "followCalc" in script
        assert "syncRangeMode" in script
        assert "computeBase" in script
        assert "_fxMode" in script
        assert "_fxZoom" in script
        assert "onPanMove" in script
        assert "jumpZoomLeft" in script
        assert "jumpZoomRight" in script
        assert '"CNY"' in script
        assert '"EUR"' in script
        assert '"JPY"' in script
        assert "USDT" not in script
        assert "/api/price-change/exchange-loss" in api_script

        # FX Calculator sub-view: sub-tabs, container, script + API constant.
        calc_script = client.get("/js/fx-calculator.js").get_data(as_text=True)
        assert 'id="fxSubTabs"' in html
        assert 'data-fx-sub="loss"' in html
        assert 'data-fx-sub="calc"' in html
        assert 'id="fxLossView"' in html
        assert 'id="fxCalcView"' in html
        assert '/js/fx-calculator.js' in html
        assert "selectFxSubView" in calc_script
        assert "renderResults" in calc_script
        assert "EXCHANGE_RATES_ENDPOINT" in calc_script
        assert "/api/price-change/exchange-rates" in api_script

        # Calculator + renamed holding P&L copy exist in both locales.
        fx_zh = client.get("/locales/zh-CN.json").get_json()["fxCalc"]
        fx_en = client.get("/locales/en.json").get_json()["fxCalc"]
        for key in ("tabLoss", "tabCalc", "amount", "baseCurrency", "comparison",
                    "copy", "addCurrency", "searchCurrency", "historyLabel"):
            assert key in fx_zh, f"zh fxCalc.{key}"
            assert key in fx_en, f"en fxCalc.{key}"
        zh_loss = client.get("/locales/zh-CN.json").get_json()["exchangeLoss"]["gainLoss"]
        en_loss = client.get("/locales/en.json").get_json()["exchangeLoss"]["gainLoss"]
        assert zh_loss == "持有盈亏（目标货币）"
        assert en_loss == "Holding P&L (target currency)"

    def test_stock_compare_has_search_tags_and_metric_tables(self, client):
        html = client.get("/zh/stock-compare").get_data(as_text=True)
        assert "年度综合收益（税后）" in html
        assert "综合年化" not in html
        assert 'id="scSymbolInput"' in html
        assert 'id="scSuggestions"' in html
        assert 'id="scQuickPicks"' in html
        assert 'id="scTags"' in html
        assert 'id="scParamsToggle"' in html
        assert 'id="scParamsPanel"' in html
        assert 'id="scMethodologyTitle"' in html
        assert 'id="scAggregateTable"' in html
        assert "先用一张聚合表纵览四项指标" not in html
        assert html.index('id="scParamsPanel"') < html.index('id="scMethodologyTitle"')
        assert html.index('id="scMethodologyTitle"') < html.index('id="scSymbolInput"')
        assert 'id="scSummary"' not in html
        assert 'id="scMetricGrid"' in html
        table_ids = [
            'id="scAggregateTable"',
            'id="scCombinedTable"',
            'id="scDrawdownTable"',
            'id="scDividendTable"',
            'id="scReturnTable"',
        ]
        assert all(table_id in html for table_id in table_ids)
        assert [html.index(table_id) for table_id in table_ids] == sorted(
            html.index(table_id) for table_id in table_ids
        )
        assert 'id="scComboChart"' not in html

        script = client.get("/js/stock-compare.js").get_data(as_text=True)
        assert '["SPY", "QQQ", "SCHD", "VGT", "SMH", "AAPL", "GOOGL"]' in script
        quick_symbols = [
            '"SCHD"', '"SPY"', '"VOO"', '"QQQ"', '"QQQM"', '"VGT"', '"XLK"',
            '"SMH"', '"SOXX"', '"AAPL"', '"MSFT"', '"GOOGL"', '"AMZN"', '"NVDA"',
            '"META"', '"TSLA"',
        ]
        quick_start = script.index("var QUICK_SYMBOLS")
        quick_end = script.index("];", quick_start)
        quick_block = script[quick_start:quick_end]
        assert [quick_block.index(symbol) for symbol in quick_symbols] == sorted(
            quick_block.index(symbol) for symbol in quick_symbols
        )
        assert "if (!_loaded && !_loading) queryComparison();" not in script
        aggregate_start = script.index("function renderAggregateTable")
        aggregate_end = script.index("function renderMetricTables", aggregate_start)
        aggregate_block = script[aggregate_start:aggregate_end]
        assert 'metricValue(result, year, symbol, "combined_annualized")' in aggregate_block
        assert 'metricValue(result, year, symbol, "max_drawdown")' in aggregate_block
        assert "dividend_yield_after_tax" not in aggregate_block
        assert '"annual_return"' not in aggregate_block
        assert "sc-aggregate-bg-return" in aggregate_block
        assert "sc-aggregate-bg-drawdown" in aggregate_block
        assert "renderAggregateTable(result);" in script

        zh_locale = client.get("/locales/zh-CN.json").get_json()
        en_locale = client.get("/locales/en.json").get_json()
        assert zh_locale["detail"]["combinedAnnualized"] == "年度综合收益（税后）"
        assert zh_locale["stockCompare"]["combinedAnnualized"] == "年度综合收益（税后）"
        assert en_locale["detail"]["combinedAnnualized"] == "Annual Combined Return (After Tax)"
        assert en_locale["stockCompare"]["combinedAnnualized"] == "Annual Combined Return (After Tax)"

    def test_return_detail_has_phase_one_overview_and_clear_statistics(self, client):
        html = client.get("/zh/detail").get_data(as_text=True)
        assert 'id="pdAssetHeader"' in html
        assert 'id="pdReturnBasisNote"' in html
        assert 'id="pdHistoryStats"' in html
        assert 'id="pdQualitySection"' in html
        assert 'id="pdFundamentalsSection"' in html
        assert 'id="pdOverviewPanel"' in html
        assert 'id="pdOverviewToggle"' in html
        assert 'aria-controls="pdOverviewPanel" aria-expanded="true"' in html
        assert 'id="pdTableTitle"' in html

        script = client.get("/js/price-detail.js").get_data(as_text=True)
        assert '"detail.cagr5y"' in script
        assert '"detail.volatility1y"' in script
        assert '"detail.historicalMaxDrawdown"' in script
        assert '"detail.winRate"' in script
        assert '"detail.sampleCount"' in script
        assert '"detail.sortinoRatio1y"' in script
        assert '"detail.trailingPe"' in script
        assert '"detail.marketCap"' in script
        assert '"detail.companyProfile"' in script
        assert '"detail.financialStatements"' in script
        assert '"detail.valuationMetrics"' in script
        assert '"detail.officialFilings"' in script
        assert '"detail.fundHoldings"' in script
        assert '"detail.cryptoMarketData"' in script
        assert '"detail.projectWebsite"' in script
        assert '"detail.whitepaper"' in script
        assert '"detail.blockExplorer"' in script
        assert '"detail.f10Profile"' in script
        assert '"detail.officialAnnouncements"' in script
        assert "https://finance.yahoo.com/quote/" in script
        assert "https://stockanalysis.com/stocks/" in script
        assert "https://stockanalysis.com/etf/" in script
        assert "https://www.sec.gov/edgar/browse/" in script
        assert "https://coinmarketcap.com/search/" in script
        assert "https://coinmarketcap.com/currencies/bitcoin/" in script
        assert "coingecko.com" not in script
        assert "https://bitcoin.org/bitcoin.pdf" in script
        assert "https://quote.eastmoney.com/" in script
        assert "https://f10.eastmoney.com/FinancialAnalysis/" in script
        assert "https://www.cninfo.com.cn/new/fulltextSearch" in script
        assert 'rel="noopener noreferrer"' in script
        assert "setOverviewCollapsed(!_overviewCollapsed)" in script
        assert '_overviewCollapsed ? "none" : "block"' in script
        assert "_stockHistoryCache" in script
        assert "nextUrl.searchParams.set(\"year\"" in script
        assert 'summary.style.display = _paramsCollapsed' not in script

        zh_locale = client.get("/locales/zh-CN.json").get_json()
        en_locale = client.get("/locales/en.json").get_json()
        assert zh_locale["detail"]["cagr5y"] == "近 5 年 CAGR"
        assert zh_locale["detail"]["winRate"] == "上涨概率"
        assert zh_locale["detail"]["fundamentalsTitle"] == "估值与市场快照"
        assert zh_locale["tab"]["returnDetail"] == "股票详情"
        assert zh_locale["detail"]["title"] == "股票详情"
        assert zh_locale["detail"]["companyProfile"] == "公司资料"
        assert zh_locale["detail"]["cryptoMarketData"] == "市场资料"
        assert zh_locale["detail"]["officialAnnouncements"] == "官方公告"
        assert "CAGR（复合年化增长率）" in zh_locale["detail"]["returnBasisStock"]
        assert zh_locale["detail"]["collapseOverview"] == "收起概览"
        assert en_locale["detail"]["cagr5y"] == "5-Year CAGR"
        assert en_locale["detail"]["winRate"] == "Win Rate"
        assert en_locale["detail"]["fundamentalsTitle"] == "Valuation & Market Snapshot"
        assert en_locale["tab"]["returnDetail"] == "Stock Detail"
        assert en_locale["detail"]["title"] == "Stock Detail"
        assert en_locale["detail"]["companyProfile"] == "Company Profile"
        assert en_locale["detail"]["cryptoMarketData"] == "Market Data"
        assert en_locale["detail"]["officialAnnouncements"] == "Official Announcements"
        assert "compound annual growth rate" in en_locale["detail"]["returnBasisStock"]
        assert en_locale["detail"]["collapseOverview"] == "Collapse overview"

    def test_stock_detail_has_fundamentals_history_shell_and_locales(self, client):
        html = client.get("/zh/detail").get_data(as_text=True)
        required_ids = [
            'id="pdFundamentalsHistory"',
            'id="pdFundamentalsHistoryTabs"',
            'id="pdFundamentalsRangeTabs"',
            'id="pdFundamentalsHistoryMeta"',
            'id="pdFundamentalsHistoryChart"',
            'id="pdFundamentalsHistoryStatus"',
        ]
        assert all(element_id in html for element_id in required_ids)
        assert html.index('id="pdFundamentalsGrid"') < html.index(
            'id="pdFundamentalsHistory"'
        )
        assert html.index('id="pdFundamentalsHistory"') < html.index(
            'id="pdFundamentalsNote"'
        )
        assert 'data-years="5"' in html
        assert 'data-years="10"' in html
        assert 'data-i18n="detail.fundamentalsHistoryTitle"' in html
        assert (
            'data-i18n-attr="aria-label|detail.fundamentalsHistoryAria"'
            in html
        )
        assert INDEX_LASTMOD == "2026-08-15"

        zh_locale = client.get("/locales/zh-CN.json").get_json()["detail"]
        en_locale = client.get("/locales/en.json").get_json()["detail"]
        expected_keys = {
            "returnOnEquity",
            "roeLatestAnnual",
            "fundamentalsHistoryTitle",
            "fundamentalsHistoryDescription",
            "fundamentalsHistory5y",
            "fundamentalsHistory10y",
            "historicalMedian",
            "historicalPercentile",
            "fundamentalsHistoryPartial",
            "fundamentalsHistoryEmpty",
            "fundamentalsHistoryLoading",
            "fundamentalsHistoryAria",
            "fundamentalsHistorySource",
            "currentValue",
            "reportDate",
        }
        assert expected_keys <= zh_locale.keys()
        assert expected_keys <= en_locale.keys()
        assert zh_locale["returnOnEquity"] == "净资产收益率（ROE）"
        assert en_locale["returnOnEquity"] == "Return on Equity (ROE)"

    def test_stock_detail_loads_and_renders_fundamentals_history(self, client):
        api_script = client.get("/js/api.js").get_data(as_text=True)
        detail_script = client.get("/js/price-detail.js").get_data(as_text=True)

        assert (
            'const FUNDAMENTALS_HISTORY_ENDPOINT = '
            '`${API_BASE}/api/price-change/fundamentals-history`;'
            in api_script
        )
        assert "_fundamentalsHistoryCache" in detail_script
        assert "_fundamentalsHistoryGeneration" in detail_script
        assert "async function loadFundamentalsHistory" in detail_script
        assert "fetch(FUNDAMENTALS_HISTORY_ENDPOINT" in detail_script
        assert "generation !== _fundamentalsHistoryGeneration" in detail_script
        assert 'quoteType === "EQUITY"' in detail_script
        assert "expiresAt" in detail_script
        assert "Date.now()" in detail_script
        assert "AbortController" in detail_script
        assert "scheduleFundamentalsHistoryResize" in detail_script
        assert '__("detail.reportDate"' in detail_script
        assert "data.return_on_equity" in detail_script
        assert "data.roe_report_date" in detail_script
        assert '"detail.roeLatestAnnual"' in detail_script
        assert '"detail.historicalMedian"' in detail_script
        assert '"detail.fundamentalsHistorySource"' in detail_script
        assert '"detail.currentValue"' in detail_script
        assert "function renderFundamentalsHistory" in detail_script
        assert "pd-fund-history-line" in detail_script
        assert "pd-fund-history-bar" in detail_script
        assert "pd-fund-history-median" in detail_script
        assert "chart.clientWidth" in detail_script
        assert "chart.clientHeight" in detail_script
        assert 'button.dataset.years' in detail_script
        assert 'metric === "roe"' in detail_script

        chart_html = client.get("/zh/detail").get_data(as_text=True)
        chart_start = chart_html.index('id="pdFundamentalsHistoryChart"')
        assert 'role="group"' in chart_html[chart_start:chart_start + 260]

    @pytest.mark.parametrize(
        "path,needle",
        [
            ("/us-etf/dram", "Roundhill official holdings"),
            ("/us-etf/qqqm", "Top 10 Holdings"),
            ("/tools/qqq-return-calculator", "btSymbolInput"),
            ("/us-etf/tqqq/historical-prices", "TQQQ Historical Prices CSV"),
            ("/knowledge/svol-volatility-premium-etf", "tracking error may not apply"),
            ("/knowledge/china-sp-500-equivalent", "CSI A500"),
            ("/knowledge/spy-volatility-history", "44 extreme trading days"),
        ],
    )
    def test_intent_landing_pages_are_server_rendered(self, client, path, needle):
        resp = client.get(f"/en{path}")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert resp.headers["X-Robots-Tag"] == "index,follow"
        assert f'<link rel="canonical" href="{SITE_URL}/en{path}"' in html
        assert needle in html

    def test_qqqm_holdings_csv_is_dated_and_downloadable(self, client):
        resp = client.get("/datasets/qqqm-holdings.csv")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment;" in resp.headers["Content-Disposition"]
        body = resp.get_data(as_text=True)
        assert "ticker,company,weight,as_of,source" in body
        assert "NVDA,NVIDIA Corp,8.01%,2026-07-10,Invesco" in body

        legacy = client.get("/api/assets/QQQM/holdings.csv")
        assert legacy.get_data() == resp.get_data()

    def test_llms_txt_links_canonical_pages_and_public_datasets(self, client):
        resp = client.get("/llms.txt")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert resp.mimetype == "text/plain"
        assert "# GlobalAssetHistory" in body
        assert f"{SITE_URL}/en/yearly" in body
        assert f"{SITE_URL}/datasets/qqqm-holdings.csv" in body
        assert f"{SITE_URL}/datasets/tqqq-historical-prices.csv" in body


# ═══════════════════════════════════════════════════════════════════════════
# Static SEO assets (og:image files must ship under frontend/ for Vercel)
# ═══════════════════════════════════════════════════════════════════════════
class TestSeoAssets:
    """og:image screenshots referenced by meta tags must exist under frontend/."""

    @pytest.fixture(scope="class")
    def screenshot_dir(self):
        return FRONTEND_DIR / "doc" / "screenshot"

    def test_yearly_heatmap_exists(self, screenshot_dir):
        assert (screenshot_dir / "yearly-heatmap.png").exists()

    def test_yearly_chart_exists(self, screenshot_dir):
        assert (screenshot_dir / "yearly-chart.png").exists()


class TestHistoricalCsv:
    def test_tqqq_csv_uses_unified_daily_series_and_filters_dates(self, client, monkeypatch):
        series = PriceSeries(
            timestamps=[1704067200, 1704153600],
            closes=[50.25, 51.75],
            source="test-source",
            fetched_at=0,
            opens=[49.0, 50.5],
            highs=[51.0, 52.0],
            lows=[48.5, 50.0],
            volumes=[1000, 1200],
        )
        monkeypatch.setattr("app._fetch_daily_series_cached", lambda symbol, asset_type: series)
        resp = client.get(
            "/datasets/tqqq-historical-prices.csv?start=2024-01-02&end=2024-01-02"
        )
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        body = resp.get_data(as_text=True)
        assert "date,open,high,low,adjusted_close,volume,source" in body
        assert "2024-01-02,50.5,52.0,50.0,51.75,1200,test-source" in body
        assert "2024-01-01" not in body

        legacy = client.get(
            "/api/assets/TQQQ/history.csv?start=2024-01-02&end=2024-01-02"
        )
        assert legacy.get_data() == resp.get_data()

    def test_tqqq_csv_rejects_invalid_date_range_without_fetching(self, client, monkeypatch):
        def unexpected_fetch(*_):
            raise AssertionError("fetch should not run")

        monkeypatch.setattr("app._fetch_daily_series_cached", unexpected_fetch)
        resp = client.get("/api/assets/TQQQ/history.csv?start=2025-02-01&end=2025-01-01")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "start must be on or before end"
