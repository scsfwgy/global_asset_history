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

from app import (
    ETF_MARKET_LASTMOD,
    FRONTEND_DIR,
    INDEX_LASTMOD,
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
        # 2 top-level pages + all knowledge articles, all en-indexable → 2 langs
        urls = _sitemap_urls(client)
        expected = (2 + len(KNOWLEDGE_ARTICLES)) * 2
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
