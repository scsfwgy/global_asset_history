"""Regression checks for remembered selections and reusable symbol search."""

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
    assert '["stock", "hk_stock", "global_stock", "crypto", "cn_stock"]' in backtest
    assert 'id="btTypeSelect"' in page
    assert 'value="hk_stock" data-i18n="yearly.assetTypeHkStock"' in page
    assert 'id="pcBtCurrency"' in page


def test_backtest_remembers_all_user_parameters():
    backtest = _source("frontend/js/backtest.js")

    assert 'const BACKTEST_PARAMS_STORAGE_KEY = "gah_backtest_params_v1";' in backtest
    assert "function saveBacktestParameters()" in backtest
    assert "function restoreBacktestParameters()" in backtest
    assert "function syncRestoredBacktestParameters()" in backtest
    assert "function initBacktestParameterPersistence()" in backtest
    assert '"pcBtAnimSeconds"' in backtest
    assert '"pcBtStartDate"' in backtest
    assert '"pcBtCompareAnim"' in backtest
    assert '"pcBtCompareStart"' in backtest
    assert '"pcBtAdvanced"' in backtest
    assert '"btShowAsset"' in backtest
    assert "localStorage.setItem(BACKTEST_PARAMS_STORAGE_KEY" in backtest
    assert "localStorage.getItem(BACKTEST_PARAMS_STORAGE_KEY)" in backtest
    assert 'panel.addEventListener("input"' in backtest
    assert 'panel.addEventListener("change"' in backtest


def test_stock_compare_backtest_start_date_defaults_and_persists():
    script = _source("frontend/js/stock-compare.js")
    page = _source("frontend/price-change.html")

    assert 'id="scStartDate" value="2021-01-01"' in page
    assert 'localStorage.setItem("gah_stock_compare_start_date"' in script
    assert 'localStorage.getItem("gah_stock_compare_start_date")' in script
    assert 'startDateInput.value = savedStartDate || "2021-01-01"' in script


def test_stock_compare_backtest_chart_shows_point_data_on_hover():
    script = _source("frontend/js/stock-compare.js")

    assert "function nearestBacktestRow(rows, targetMs)" in script
    assert 'id=\\"scBacktestHoverPlot\\"' in script
    assert 'id=\\"scBacktestTooltip\\"' in script
    assert 'hoverPlot.addEventListener("pointermove"' in script
    assert 'hoverPlot.addEventListener("pointerleave"' in script
    assert "formatChartNumber(row.total_return_pct)" in script


def test_crash_stats_remembers_symbol_and_asset_type():
    source = _source("frontend/js/crash-stats.js")
    page = _source("frontend/price-change.html")

    assert 'const CRASH_SYMBOL_STORAGE_KEY = "gah_crash_symbol";' in source
    assert "function saveSymbolPreference(symbol, type)" in source
    assert "function restoreSymbolPreference()" in source
    assert "restoreSymbolPreference();" in source
    assert 'symbolInput.addEventListener("input", saveCurrentPreference)' in source
    assert '["stock", "hk_stock", "global_stock", "crypto", "cn_stock"]' in source
    assert 'id="crashType"' in page
    assert 'value="hk_stock" data-i18n="yearly.assetTypeHkStock"' in page


def test_data_download_remembers_all_user_selected_parameters_immediately():
    source = _source("frontend/js/data-download.js")
    page = _source("frontend/price-change.html")

    assert 'var DOWNLOAD_STATE_STORAGE_KEY = "gah_download_state";' in source
    assert "function saveState()" in source
    assert "function restoreState()" in source
    assert "localStorage.setItem(DOWNLOAD_STATE_STORAGE_KEY" in source
    assert "localStorage.getItem(DOWNLOAD_STATE_STORAGE_KEY)" in source
    for field in ("symbol", "type", "period", "start_date", "end_date", "global_symbol"):
        assert field in source
    assert '$("downloadSymbolInput").addEventListener("input", saveState)' in source
    assert '$("downloadStartDate").addEventListener("change", saveState)' in source
    assert "DOWNLOAD_ASSET_TYPES.indexOf(saved.type)" in source
    assert "DOWNLOAD_PERIODS.indexOf(saved.period)" in source
    assert 'id="downloadGlobalSymbolSelect"' in page


def test_symbol_inputs_use_remote_company_name_search_with_local_fallback():
    api = _source("frontend/js/api.js")
    source = _source("frontend/js/price-change.js")
    page = _source("frontend/price-change.html")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    assert "SYMBOL_SEARCH_ENDPOINT" in api
    assert "loadRemoteSuggestions" in source
    assert "fetch(url)" in source
    assert "encodeURIComponent(type" in source
    assert "_acMerge(remoteItems, localItems)" in source
    assert "#downloadGlobalSymbolSelect option[value]" in source
    assert "type: 'global_stock'" in source
    assert "_acEscape(details)" in source
    assert "}, 250);" in source
    for input_id in (
        "pcSymbolInput", "pdSymbolInput", "downloadSymbolInput", "btSymbolInput", "crashSymbol",
    ):
        assert f"document.getElementById('{input_id}')" in source
    assert 'data-i18n="download.symbolSearchHint"' in page
    assert "公司名称或代码" in zh_locale["download"]["symbolSearchHint"]
    assert "company name or symbol" in en_locale["download"]["symbolSearchHint"].lower()

    style_start = page.index("\n        .pc-ac-item {\n")
    style_end = page.index("\n        }", style_start)
    autocomplete_style = page[style_start:style_end]
    for rule in (
        "border: 0",
        "appearance: none",
        "-webkit-appearance: none",
        "background: transparent",
        "color: var(--apple-text-primary)",
    ):
        assert rule in autocomplete_style


def test_hk_and_global_stocks_are_available_across_analysis_modules():
    page = _source("frontend/price-change.html")
    yearly = _source("frontend/js/price-change.js")
    detail = _source("frontend/js/price-detail.js")
    backtest = _source("frontend/js/backtest.js")
    crash = _source("frontend/js/crash-stats.js")
    heatmap = _source("frontend/js/heatmap.js")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    assert 'id="pcTypeSelect"' in page
    assert 'id="pdTypeSelect"' in page
    assert page.count('value="hk_stock" data-i18n="yearly.assetTypeHkStock"') >= 4
    assert page.count('value="global_stock" data-i18n="yearly.assetTypeGlobalStock"') == 4
    assert "function normalizeAssetSymbol(symbol, type)" in yearly
    assert 's.type === "global_stock" ? __("yearly.labelGlobal")' in yearly
    assert '["stock", "hk_stock", "global_stock"]' in detail
    assert '["stock", "hk_stock", "global_stock", "crypto", "cn_stock"]' in backtest
    assert '["stock", "hk_stock", "global_stock", "crypto", "cn_stock"]' in crash
    assert "typeSelect.value = 'global_stock'" in heatmap
    for input_id in ("pcSymbolInput", "pdSymbolInput", "btSymbolInput", "crashSymbol"):
        input_markup = page.split(f'id="{input_id}"', 1)[1].split(">", 1)[0]
        assert 'maxlength="30"' in input_markup
    assert 'currencyDisplay: "symbol"' in detail
    assert zh_locale["yearly"]["assetTypeHkStock"] == "港股"
    assert zh_locale["yearly"]["labelHK"] == "港"
    assert zh_locale["yearly"]["assetTypeGlobalStock"] == "全球股票"
    assert zh_locale["yearly"]["labelGlobal"] == "全球"
    assert en_locale["yearly"]["assetTypeHkStock"] == "HK Stock"
    assert en_locale["yearly"]["labelHK"] == "HK"
    assert en_locale["yearly"]["assetTypeGlobalStock"] == "Global Stock"
    assert en_locale["yearly"]["labelGlobal"] == "Global"


def test_data_download_supports_hk_and_global_stocks():
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/data-download.js")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    assert 'id="downloadTypeSelect"' in page
    assert 'value="hk_stock" data-i18n="yearly.assetTypeHkStock"' in page
    assert 'value="global_stock" data-i18n="download.assetTypeGlobalStock"' in page
    assert 'id="downloadGlobalSymbolSelect"' in page
    assert "#tab-download .control-group" in page
    assert "flex-wrap: wrap;" in page
    assert page.count('<option value=') >= 30
    for symbol in ("7203.T", "005930.KS", "2330.TW", "ASML.AS", "2222.SR"):
        assert f'value="{symbol}"' in page
    assert '=== "global_stock"' in script
    assert '$("downloadSymbolInput").value = this.value' in script
    assert zh_locale["download"]["assetTypeGlobalStock"] == "全球股票"
    assert en_locale["download"]["assetTypeGlobalStock"] == "Global Stock"
    assert en_locale["download"]["period1m"] == "1 Min"
    assert "2330.TW" in zh_locale["download"]["globalSymbolHint"]
