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
    for market_type in ("stock", "crypto", "cn_stock"):
        assert f'value="{market_type}"' in page
    assert zh_locale["heatmap"]["emptyPrompt"] == "点击「查询」查看市场热力图"
    assert (
        en_locale["heatmap"]["emptyPrompt"]
        == 'Click "Query" to view the market heatmap'
    )


def test_backtest_remembers_symbol_and_asset_type():
    backtest = _source("frontend/js/backtest.js")

    assert 'const BACKTEST_SYMBOL_STORAGE_KEY = "gah_backtest_symbol";' in backtest
    assert "function saveBacktestSymbol(symbol, type)" in backtest
    assert "function restoreBacktestSymbol()" in backtest
    assert "function initBacktestSymbolPersistence()" in backtest
    assert (
        'document.addEventListener("DOMContentLoaded", '
        "initBacktestSymbolPersistence)"
    ) in backtest
    assert 'btSymbolInput.addEventListener("input", saveCurrentPreference)' in backtest


def test_crash_stats_remembers_symbol_and_asset_type():
    source = _source("frontend/js/crash-stats.js")

    assert 'const CRASH_SYMBOL_STORAGE_KEY = "gah_crash_symbol";' in source
    assert "function saveSymbolPreference(symbol, type)" in source
    assert "function restoreSymbolPreference()" in source
    assert "restoreSymbolPreference();" in source
    assert 'symbolInput.addEventListener("input", saveCurrentPreference)' in source
