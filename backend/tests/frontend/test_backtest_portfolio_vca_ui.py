"""Regression checks for portfolio backtesting and Value Averaging (VCA) UI contracts."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_backtest_detail_supports_portfolio_and_vca_controls():
    page = _source("frontend/price-change.html")
    script = _source("frontend/js/backtest.js")
    zh_cn = json.loads(_source("frontend/locales/zh-CN.json"))["backtest"]
    zh_tw = json.loads(_source("frontend/locales/zh-TW.json"))["backtest"]
    en = json.loads(_source("frontend/locales/en.json"))["backtest"]

    for dom_id in (
        "pcBtTargetMode",
        "btSingleAssetWrap",
        "btPortfolioMetaWrap",
        "pcBtBaseCurrency",
        "pcBtRebalance",
        "pcBtPortfolioPanel",
        "pcBtPortfolioPresets",
        "pcBtPortfolioAdd",
        "pcBtPortfolioEqual",
        "pcBtWeightSum",
        "pcBtPortfolioRows",
        "pcBtStrategy",
        "pcBtVcaFields",
        "pcBtVcaSellMode",
        "pcBtVcaGrowthRate",
        "pcBtVcaMaxContrib",
        "pcBtStrategyGuide",
        "pcBtNotice",
        "pcBtHoldingsWrap",
        "pcBtHoldingsHead",
        "pcBtHoldingsBody",
    ):
        assert f'id="{dom_id}"' in page, dom_id
        assert dom_id in script, dom_id

    for fn_name in (
        "updateBacktestModeUI",
        "updateBacktestStrategyUI",
        "readPortfolioRows",
        "setPortfolioRows",
        "equalizePortfolioWeights",
        "renderPortfolioHoldings",
        "renderBacktestNotice",
        "formatBtKindBadge",
    ):
        assert f"function {fn_name}" in script, fn_name

    # VCA target curve series and legend integration
    assert 'data-series="target"' in script
    assert "btSeries-target" in script
    assert "btTooltipTarget" in script

    # Trilingual locale completeness for new keys
    required_keys = {
        "targetMode", "modeSingle", "modePortfolio", "baseCurrency",
        "rebalance", "rebalanceNone", "rebalanceMonthly", "rebalanceQuarterly",
        "rebalanceYearly", "rebalanceCountNote", "portfolioPresets",
        "preset6040", "presetAllWeather", "presetTechGoldBtc", "presetUsCn",
        "portfolioAdd", "portfolioEqual", "weightSumLabel",
        "strategyDca", "strategyVca", "frequency", "vcaExceedRule",
        "vcaAllowSell", "vcaNoSell", "vcaGrowthRate", "vcaGrowthTooltip",
        "vcaMaxCap", "vcaMaxCapTooltip", "vcaUnlimited", "labelVcaIncrement",
        "targetValue", "netInvested", "netInvestedNote",
        "totalReturnRatePeakNote", "tradeCountVcaNote", "tradeCountPortfolioNote",
        "holdingsTitle", "colAsset", "colNativeCcy", "colTargetWeight",
        "colFinalWeight", "colLastPriceBase", "colFinalValue", "colTargetValue",
        "colNetInvested", "colPortfolioValue", "colAllocation",
        "kindVcaBuy", "kindVcaSell", "kindVcaHold", "kindRebalance",
        "noticeStartDateShifted", "noticeVcaSummary", "errorVcaIncrement",
        "errorPortfolioMinAssets", "errorPortfolioWeightInvalid",
        "errorPortfolioWeightSum",
        "guideDcaTitle", "guideDcaTag", "guideDcaDesc",
        "guideVcaTitle", "guideVcaTag", "guideVcaDesc",
    }
    assert 'data-strategy-card="dca"' in page
    assert 'data-strategy-card="vca"' in page
    for locale_name, locale_dict in (("zh-CN", zh_cn), ("zh-TW", zh_tw), ("en", en)):
        missing = required_keys - locale_dict.keys()
        assert not missing, f"{locale_name} missing keys: {missing}"
