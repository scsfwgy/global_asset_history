"""Regression checks for locally remembered user-entered asset symbols."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_heatmap_uses_market_types_without_symbol_or_top_n_controls():
    script = _source("frontend/js/heatmap.js")
    page = _source("frontend/price-change.html")
    styles = _source("frontend/css/app.css")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    for identifier in (
        "hmSymbolInput",
        "hmTypeSelect",
        "hmAddBtn",
        "hmClearBtn",
        "hmTags",
        "_hmSymbols",
        "HM_STORAGE_KEY",
    ):
        assert identifier not in script
        assert identifier not in page

    assert "symbols: []" in script
    assert 'id="hmMarketType"' in page
    assert "market_type: hmMarketType.value" in script
    assert 'const HM_FILTER_STORAGE_KEY = "gah_heatmap_filters";' in script
    assert "function saveHmFilters()" in script
    assert "function restoreHmFilters()" in script
    assert "localStorage.setItem(HM_FILTER_STORAGE_KEY" in script
    assert "localStorage.getItem(HM_FILTER_STORAGE_KEY)" in script
    assert "restoreHmFilters();" in script
    for field in ("market_type", "period", "size_by"):
        assert f"{field}:" in script
    assert 'id="hmTopN"' not in page
    assert "auto_top_n" not in script
    assert "#hmFilterPanel .control-group" in styles
    assert "flex-wrap: wrap;" in styles
    for market_type in ("stock", "hk_stock", "global_stock", "crypto", "cn_stock"):
        assert f'value="{market_type}"' in page
    assert '["stock", "hk_stock", "global_stock", "crypto", "cn_stock"]' in script
    assert "d.type === 'hk_stock'" in script
    assert 'd.market_cap_currency || d.turnover_currency' in script
    assert 'hmMarketType.value === "global_stock"' in script
    assert 'result.market_type === "global_stock"' in script
    assert 'hmSizeBySel.value = "return"' in script
    assert 'data-market="' in script
    assert zh_locale["heatmap"]["marketHK"] == "港股市场"
    assert en_locale["heatmap"]["marketHK"] == "Hong Kong Market"
    assert zh_locale["heatmap"]["marketGlobal"] == "全球热门股票"
    assert en_locale["heatmap"]["marketGlobal"] == "Global Stocks"
    assert zh_locale["heatmap"]["emptyPrompt"] == "点击「查询」查看市场热力图"
    assert (
        en_locale["heatmap"]["emptyPrompt"]
        == 'Click "Query" to view the market heatmap'
    )


def test_backtest_remembers_symbol_and_asset_type():
    backtest = _source("frontend/js/backtest.js")
    page = _source("frontend/price-change.html")

    assert 'const BACKTEST_SYMBOL_STORAGE_KEY = "gah_backtest_symbol";' in backtest
    assert "function saveBacktestSymbol(symbol, type)" in backtest
    assert "function restoreBacktestSymbol()" in backtest
    assert "function initBacktestSymbolPersistence()" in backtest
    assert (
        'document.addEventListener("DOMContentLoaded", '
        "initBacktestSymbolPersistence)"
    ) in backtest
    assert 'btSymbolInput.addEventListener("input", saveCurrentPreference)' in backtest
    assert '["stock", "hk_stock", "crypto", "cn_stock"]' in backtest
    assert 'id="btTypeSelect"' in page
    assert 'value="hk_stock" data-i18n="yearly.assetTypeHkStock"' in page
    assert 'id="pcBtCurrency"' in page


def test_crash_stats_remembers_symbol_and_asset_type():
    source = _source("frontend/js/crash-stats.js")
    page = _source("frontend/price-change.html")

    assert 'const CRASH_SYMBOL_STORAGE_KEY = "gah_crash_symbol";' in source
    assert "function saveSymbolPreference(symbol, type)" in source
    assert "function restoreSymbolPreference()" in source
    assert "restoreSymbolPreference();" in source
    assert 'symbolInput.addEventListener("input", saveCurrentPreference)' in source
    assert '["stock", "hk_stock", "crypto", "cn_stock"]' in source
    assert 'id="crashType"' in page
    assert 'value="hk_stock" data-i18n="yearly.assetTypeHkStock"' in page


def test_hk_stock_is_available_in_history_and_detail_with_bilingual_labels():
    page = _source("frontend/price-change.html")
    yearly = _source("frontend/js/price-change.js")
    detail = _source("frontend/js/price-detail.js")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    assert 'id="pcTypeSelect"' in page
    assert 'id="pdTypeSelect"' in page
    assert page.count('value="hk_stock" data-i18n="yearly.assetTypeHkStock"') >= 4
    assert "function normalizeAssetSymbol(symbol, type)" in yearly
    assert 'currencyDisplay: "symbol"' in detail
    assert zh_locale["yearly"]["assetTypeHkStock"] == "港股"
    assert zh_locale["yearly"]["labelHK"] == "港"
    assert en_locale["yearly"]["assetTypeHkStock"] == "HK Stock"
    assert en_locale["yearly"]["labelHK"] == "HK"
