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

import os
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
        """Every <loc> must carry a /zh or /en prefix — the no-prefix variant
        canonicalizes to /zh, so listing it creates a duplicate Google flags."""
        urls = _sitemap_urls(client)
        locs = [u.findtext(f"{SITEMAP_NS}loc") for u in urls]
        assert locs, "sitemap should not be empty"
        for loc in locs:
            assert f"{SITE_URL}/zh" in loc or f"{SITE_URL}/en" in loc, (
                f"no-prefix URL leaked into sitemap: {loc}"
            )

    def test_no_duplicate_locs(self, client):
        locs = [u.findtext(f"{SITEMAP_NS}loc") for u in _sitemap_urls(client)]
        assert len(locs) == len(set(locs)), "duplicate loc in sitemap"

    def test_url_count_matches_pages_times_languages(self, client):
        # Top-level pages, indexable tools, articles and intent landing pages.
        urls = _sitemap_urls(client)
        expected = (2 + len(INDEXABLE_TOOL_PATHS) + len(KNOWLEDGE_ARTICLES)) * 2
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
            if loc.endswith("/zh/") or loc.endswith("/en/"):
                assert u.findtext(f"{SITEMAP_NS}lastmod") == INDEX_LASTMOD

    def test_each_url_has_full_hreflang_set(self, client):
        for u in _sitemap_urls(client):
            hreflangs = {a.get("hreflang") for a in u.findall(f"{XHTML_NS}link")}
            assert {"zh-CN", "en", "x-default"} <= hreflangs


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
            'og:image" content="https://test.local/doc/screenshot/yearly-heatmap.png"'
            in html
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/knowledge/how-to-buy-us-stocks",
            "/knowledge/value-investing",
            "/knowledge/nasdaq-etf-guide",
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

    @pytest.mark.parametrize("path", ["/yearly", "/detail", "/backtest"])
    def test_indexable_tools_have_self_canonical_and_consistent_robots(self, client, path):
        resp = client.get(f"/en{path}")
        html = resp.get_data(as_text=True)
        assert resp.headers["X-Robots-Tag"] == "index,follow"
        assert 'name="robots" content="index,follow"' in html
        assert f'<link rel="canonical" href="{SITE_URL}/en{path}"' in html

    def test_tool_navigation_uses_crawlable_language_links(self, client):
        html = client.get("/en/backtest").get_data(as_text=True)
        assert '<a class="tab-btn" href="/en/yearly"' in html
        assert '<a class="tab-btn" href="/en/backtest"' in html
        assert html.count('class="header-quick-link"') == 2
        assert '<a class="header-quick-link" href="/en/knowledge/value-investing"' in html
        assert '<a class="header-quick-link" href="/en/knowledge/how-to-buy-us-stocks"' in html
        assert "__LANG_PREFIX__" not in html

    @pytest.mark.parametrize(
        "path,needle",
        [
            ("/us-etf/dram", "Roundhill official holdings"),
            ("/us-etf/qqqm", "Top 10 Holdings"),
            ("/tools/qqq-return-calculator", "btSymbolInput"),
            ("/us-etf/tqqq/historical-prices", "TQQQ Historical Prices CSV"),
            ("/knowledge/svol-volatility-premium-etf", "tracking error may not apply"),
            ("/knowledge/china-sp-500-equivalent", "CSI A500"),
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
        resp = client.get("/api/assets/QQQM/holdings.csv")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment;" in resp.headers["Content-Disposition"]
        body = resp.get_data(as_text=True)
        assert "ticker,company,weight,as_of,source" in body
        assert "NVDA,NVIDIA Corp,8.01%,2026-07-10,Invesco" in body


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
        resp = client.get("/api/assets/TQQQ/history.csv?start=2024-01-02&end=2024-01-02")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        body = resp.get_data(as_text=True)
        assert "date,open,high,low,adjusted_close,volume,source" in body
        assert "2024-01-02,50.5,52.0,50.0,51.75,1200,test-source" in body
        assert "2024-01-01" not in body

    def test_tqqq_csv_rejects_invalid_date_range_without_fetching(self, client, monkeypatch):
        def unexpected_fetch(*_):
            raise AssertionError("fetch should not run")

        monkeypatch.setattr("app._fetch_daily_series_cached", unexpected_fetch)
        resp = client.get("/api/assets/TQQQ/history.csv?start=2025-02-01&end=2025-01-01")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "start must be on or before end"
