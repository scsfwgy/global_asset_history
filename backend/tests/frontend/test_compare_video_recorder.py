"""Regression checks for the backtest compare video recorder (chart + legend)."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_compare_recorder_uses_offscreen_canvas_and_native_mediarecorder():
    script = _source("frontend/js/backtest.js")
    page = _source("frontend/price-change.html")
    zh_locale = json.loads(_source("frontend/locales/zh-CN.json"))
    en_locale = json.loads(_source("frontend/locales/en.json"))

    # Recorder wiring: button on the compare toolbar, module snapshot + entry point.
    assert 'id="btCmpRecord"' in page
    assert "btCmpRecord" in script
    assert "_btCompareLast" in script
    assert "recordCompareVideo" in script
    assert "initCompareRecorder" in script

    # Orientation lives in the compare params panel and drives BOTH the on-page
    # chart geometry and the recording, so the video stays in sync with the chart.
    assert 'id="pcBtCompareOrientation"' in page
    assert "btCmpRecOrientation" not in page
    assert "_btCompareOrientation" in script
    assert "_btCompareLastInputs" in script
    for token in (
        "BT_RECORD_PORTRAIT_W",
        "BT_RECORD_PORTRAIT_H",
        "BT_RECORD_LANDSCAPE_W",
        "BT_RECORD_LANDSCAPE_H",
        "_btCompareOrientation === \"portrait\"",
        'var W = portrait ? 360 : 700',
        'var H = portrait ? 440 : 280',
        'data-orientation',
        "state.axisFont",
        "renderBtCompareChart(_btCompareLastInputs.series, _btCompareLastInputs.context)",
    ):
        assert token in script, token
    assert "BT_RECORD_PORTRAIT_W = 1080" in script
    assert "BT_RECORD_PORTRAIT_H = 1920" in script
    assert "BT_RECORD_LANDSCAPE_W = 1920" in script
    assert "BT_RECORD_LANDSCAPE_H = 1080" in script
    assert '#btCompareChart[data-orientation="portrait"]' in page
    assert '#btCompareChart[data-orientation="landscape"]' in page

    # Native capture path: no canvas-to-video library, no backend.
    for token in (
        "canvas.captureStream(",
        "new MediaRecorder(",
        "MediaRecorder.isTypeSupported(",
        "svgToImage",
        "buildCompareAxisSvg",
        "buildCompareLinesSvg",
        "layoutCompareLegendItems",
        "BT_RECORD_LANDSCAPE_W",
        "BT_RECORD_MIN_MS",
        "BT_RECORD_HOLD_MS",
    ):
        assert token in script, token

    # Video legend uses logical chart units, then scales once to the native
    # canvas. Text measurements must not be multiplied by the scale a second time.
    for token in (
        "BT_LEGEND_ITEM_GAP",
        "BT_LEGEND_FLEX_GAP",
        "BT_LEGEND_PCT_MIN_W",
        "BT_LEGEND_TITLE_SIZE",
        "BT_LEGEND_ITEM_SIZE",
        "BT_LEGEND_OVERLAY_ALPHA",
    ):
        assert token in script, token
    assert "var ls = scale" in script
    assert "codeW + valW + pctW" in script
    assert "codeW +\n             (BT_LEGEND_CODE_MR" not in script

    # H.264 MP4 (plays everywhere incl. iOS) must be preferred over webm; the
    # explicit avc1 codec keeps Chrome from emitting VP9-in-mp4.
    assert "video/mp4;codecs=avc1.42E01E" in script
    assert script.index("avc1") < script.index("video/webm")

    # The video draws chart + legend only; page chrome must not be recorded.
    assert "drawCompareLegend" in script

    # Brand watermark appears on both the on-page chart and the recorded video.
    assert "BT_BRAND_TEXT" in script
    assert "https://qqq.tools24.uk" in script
    assert "buildBtBrandSvg" in script
    # detail chart + compare on-page + recording axis = 3 call sites
    assert script.count("buildBtBrandSvg(") >= 3

    # Video is rasterized at the native canvas resolution (not upscaled from the
    # 700x280 SVG), so text stays crisp.
    assert "buildCompareAxisSvg(state, chartW, chartH)" in script
    assert "buildCompareLinesSvg(state, chartW, chartH)" in script
    assert 'width="${chartW}"' in script

    # Reveal progress is clamped to [0,1] so a slightly-early rAF timestamp never
    # sets a negative rect width.
    assert "Math.max(0, Math.min((now - start) / durMs, 1))" in script

    # Faint horizontal grid lines shared by the page chart and the video.
    assert "BT_GRID_STROKE" in script
    assert script.count("BT_GRID_STROKE") >= 2

    # Detail, compare, and recorder share the same quiet axis builder and line
    # tokens. The first/last X labels use edge-safe anchors.
    assert script.count("buildBtAxes({") >= 3
    assert "BT_PRIMARY_LINE_STROKE" in script
    assert "BT_SECONDARY_LINE_STROKE" in script
    assert "BT_AXIS_FONT" in script
    assert "BT_AXIS_LINE_STROKE" in script
    assert "labelColor = state.textSecondary" in script
    assert 'stroke-width="${BT_AXIS_LINE_STROKE}"' in script
    assert 'index === 0 ? "start"' in script
    assert 'config.xTicks.length - 1 ? "end"' in script

    # Multi-symbol curves are aligned on real dates, not independent point indexes.
    assert "btDateMs" in script
    assert "xPosMs" in script
    assert "minDateMs" in script
    assert "dateRangeMs" in script
    assert "interpolateBtPointAtX" in script
    assert "maxLen" not in script

    # Every frame is pre-filled with the theme background and the legend is
    # overlaid on the full-height plot instead of reserving a large footer.
    assert "ctx.fillStyle = videoState.bg;" in script
    assert "ctx.fillRect(0, 0, canvas.width, canvas.height);" in script
    assert "buildCompareVideoState" in script
    assert "var chartH = canvasH" in script
    assert "BT_LEGEND_OVERLAY_ALPHA" in script
    assert '__("backtest.shareDisclaimer")' not in script

    # Backtest errors must render in a visible box: the shared yearly #pcError
    # sits inside the hidden #tab-yearly panel while the backtest tab is active.
    assert 'id="btError"' in page
    assert "function btError" in script
    assert "showError(" not in script

    # i18n keys exist in both locales.
    for key in ("record", "recordLandscape", "recordPortrait", "recordRecording",
                "recordUnsupported", "recordNeedRun", "orientation"):
        assert key in zh_locale["backtest"], key
        assert key in en_locale["backtest"], key
    assert zh_locale["backtest"]["record"] == "录制视频"
    assert en_locale["backtest"]["record"] == "Record video"
    assert zh_locale["backtest"]["recordLandscape"] == "横屏"
    assert zh_locale["backtest"]["recordPortrait"] == "竖屏"
    assert zh_locale["backtest"]["compareCardTitle"].startswith("一次性投入")
    assert "shareDisclaimer" not in zh_locale["backtest"]
    assert "shareDisclaimer" not in en_locale["backtest"]
    assert zh_locale["backtest"]["recordUnsupported"].startswith("当前浏览器不支持录制视频")
    assert en_locale["backtest"]["recordUnsupported"].startswith("Video recording is not supported")
