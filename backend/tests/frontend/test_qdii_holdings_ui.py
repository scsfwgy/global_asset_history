"""Static integration checks for the lazy QDII holdings table UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_qdii_table_exposes_region_column_and_23_column_detail_row():
    page = _source("frontend/price-change.html")

    assert 'data-i18n="qdii.colRegions"' in page
    assert 'id="qdiiFundsBody"' in page
    assert 'colspan="23"' in page
    assert ".qdii-holdings-detail-row" in page


def test_qdii_holdings_are_lazy_loaded_and_render_fund_positions():
    api = _source("frontend/js/api.js")
    script = _source("frontend/js/qdii-funds.js")

    assert "QDII_FUND_HOLDINGS_ENDPOINT" in api
    assert 'data-qdii-holdings-code="' in script
    assert '"/holdings"' in script
    assert "renderHoldingsDetail" in script
    assert "data.fund_positions" in script
    assert "data.region_summary" in script


def test_qdii_holdings_copy_exists_in_both_locales():
    zh = _source("frontend/locales/zh-CN.json")
    en = _source("frontend/locales/en.json")

    for locale in (zh, en):
        assert '"colRegions"' in locale
        assert '"holdingsMethod"' in locale
        assert '"holdingsFundPositions"' in locale
