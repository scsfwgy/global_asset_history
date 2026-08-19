"""Static integration checks for the ETF historical returns matrix UI."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOCALE_KEYS = {
    "returnsHistory",
    "returnsAnnual",
    "returnsMonthly",
    "returnsYear",
    "returnsLoading",
    "returnsLoadFailed",
    "returnsNoData",
    "returnsPartial",
    "returnsLoaded",
    "returnsWithPremium",
    "returnsWithoutPremium",
    "returnsNoteTitle",
    "returnsNoteWithPremium",
    "returnsNoteWithoutPremium",
    "returnsNoteCaution",
    "returnsSymbol",
    "returnsMonth",
}


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_matrix_is_appended_after_existing_aggregate_chart():
    page = _source("frontend/price-change.html")

    assert page.index('id="etfAggregateChart"') < page.index('id="etfReturnsMatrix"')
    assert 'id="etfReturnsModes"' in page
    assert 'data-etf-returns-mode="year"' in page
    assert 'data-etf-returns-mode="month"' in page
    assert 'id="etfReturnsYear"' in page
    assert 'data-i18n="etf.returnsNoteWithPremium"' in page
    assert 'data-i18n="etf.returnsNoteWithoutPremium"' in page
    assert 'data-i18n="etf.returnsNoteCaution"' in page


def test_matrix_keeps_old_chart_flow_and_has_independent_request():
    script = _source("frontend/js/etf-market.js")

    assert 'return _activeTab + ":120"' in script
    assert '"&days=120"' in script
    assert '"/api/etf-market/returns-matrix?group="' in script
    assert '"&mode=" + encodeURIComponent(_returnsMode)' in script
    assert '"&year=" + encodeURIComponent(_returnsYear)' in script
    assert script.count("ensureReturnsMatrix(false);") >= 5


def test_matrix_renders_both_metrics_and_handles_missing_and_stale_data():
    script = _source("frontend/js/etf-market.js")

    assert 'buildReturnsTable(data, "with_premium"' in script
    assert 'buildReturnsTable(data, "without_premium"' in script
    assert 'return "--"' in script
    assert "row.benchmark" in script
    assert 'returnsCacheKey() === key' in script
    assert 'returnsCacheKey() !== key' in script
    assert "escapeHtml(row.symbol)" in script
    assert "escapeHtml(row.name)" in script


def test_matrix_copy_exists_in_all_locales():
    for path in (
        "frontend/locales/zh-CN.json",
        "frontend/locales/zh-TW.json",
        "frontend/locales/en.json",
    ):
        etf = json.loads(_source(path))["etf"]
        assert LOCALE_KEYS <= etf.keys()
        assert "{{count}}" in etf["returnsPartial"]
        assert "{{month}}" in etf["returnsMonth"]
