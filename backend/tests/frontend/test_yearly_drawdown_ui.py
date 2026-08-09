"""Static integration checks for yearly/monthly return and drawdown cells."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_yearly_page_exposes_persisted_return_drawdown_display_mode():
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/price-change.js")
    styles = _source("frontend/css/app.css")

    assert 'id="pcMetricDisplay"' in page
    assert 'value="combined" data-i18n="yearly.displayCombined"' in page
    assert 'value="return" data-i18n="yearly.displayReturnOnly"' in page
    assert 'metricDisplay: metricDisplay ? metricDisplay.value : "combined"' in script
    assert '["combined", "return"].includes(state.metricDisplay)' in script
    assert 'metricDisplay.addEventListener("change"' in script
    assert ".pc-return-stack" in styles
    assert ".pc-cell-drawdown" in styles


def test_yearly_and_monthly_cells_render_drawdown_with_dates_and_csv_columns():
    yearly = _source("frontend/js/price-change.js")
    drilldown = _source("frontend/js/drilldown.js")

    assert "function metricCellMarkup(returnValue, drawdownEntry)" in yearly
    assert 'drawdownEntry.peak_date && drawdownEntry.trough_date' in yearly
    assert 'drawdowns[sym] && drawdowns[sym][year]' in yearly
    assert 'monthDrawdownMap[sym][m.month] = m' in yearly
    assert 'drawdowns[sym] && drawdowns[sym][String(year)]' in yearly
    assert 'sym + " " + __("yearly.maxDrawdown")' in yearly
    assert "metricCellMarkup(val, m)" in drilldown


def test_drawdown_copy_is_complete_in_both_languages():
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["yearly"]
    en = json.loads(_source("frontend/locales/en.json"))["yearly"]

    expected = {
        "cellDisplay",
        "displayCombined",
        "displayReturnOnly",
        "returnShort",
        "drawdownShort",
        "returnLabel",
        "maxDrawdown",
        "drawdownRange",
    }
    assert expected <= zh.keys()
    assert expected <= en.keys()
    assert "最大回撤" in zh["emptyPrompt"]
    assert "max drawdowns" in en["emptyPrompt"]


def test_drawdown_risk_levels_follow_global_negative_color_semantics():
    yearly = _source("frontend/js/price-change.js")
    chart = _source("frontend/js/charts.js")
    styles = _source("frontend/css/app.css")

    assert "function drawdownRiskClass(value)" in yearly
    assert 'value >= -5) return "pc-drawdown-neutral"' in yearly
    assert 'value >= -10) return "pc-drawdown-mild"' in yearly
    assert 'value >= -20) return "pc-drawdown-moderate"' in yearly
    assert 'value >= -35) return "pc-drawdown-severe"' in yearly
    assert 'return "pc-drawdown-extreme"' in yearly
    assert 'pc-cell-drawdown ${drawdownClass}' in yearly
    assert 'pc-chart-tooltip-value ${drawdownRiskClass(drawdown)}' in chart
    for class_name in (
        ".pc-drawdown-neutral",
        ".pc-drawdown-mild",
        ".pc-drawdown-moderate",
        ".pc-drawdown-severe",
        ".pc-drawdown-extreme",
    ):
        assert class_name in styles
    assert "var(--data-negative)" in styles


def test_yearly_chart_exposes_focus_scale_tooltip_and_external_legend():
    page = _source("frontend/price-change.html")
    styles = _source("frontend/css/app.css")

    for element_id in (
        "pcChartScaleFocus",
        "pcChartScaleFull",
        "pcChartScaleNote",
        "pcChartPlot",
        "pcChartTooltip",
        "pcChartLegend",
    ):
        assert f'id="{element_id}"' in page

    assert ".pc-chart-scale-toggle" in styles
    assert ".pc-chart-tooltip" in styles
    assert ".pc-chart-legend" in styles
    assert "#pcChartSvg { min-width: 620px; }" in styles


def test_yearly_chart_renders_stable_color_return_drawdown_panels():
    chart = _source("frontend/js/charts.js")
    yearly = _source("frontend/js/price-change.js")

    assert "function computeChartRange(values, mode)" in chart
    assert 'mode === "focus"' in chart
    assert 'LINE_COLORS[series.index % LINE_COLORS.length]' in chart
    assert "LINE_COLORS[vi % LINE_COLORS.length]" not in chart
    assert "function renderReturnPanel(" in chart
    assert "function renderDrawdownPanel(" in chart
    assert 'data-chart-point="1"' in chart
    assert "function renderChartLegend(" in chart
    assert "function bindChartTooltip()" in chart
    assert "renderMultiLineChart(data, activeSymbols, [], drawdowns)" in yearly
    assert "renderMonthlyChart(year, symKeys, monthMap, monthDrawdownMap)" in yearly


def test_chart_copy_is_complete_in_both_languages():
    zh = json.loads(_source("frontend/locales/zh-CN.json"))["chart"]
    en = json.loads(_source("frontend/locales/en.json"))["chart"]

    expected = {
        "scaleMode",
        "focusScale",
        "fullScale",
        "focusedOutliers",
        "returnPanel",
        "drawdownPanel",
        "showAll",
        "legendHint",
    }
    assert expected <= zh.keys()
    assert expected <= en.keys()
