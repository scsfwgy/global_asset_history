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

    # Native capture path: no canvas-to-video library, no backend.
    for token in (
        "canvas.captureStream(",
        "new MediaRecorder(",
        "MediaRecorder.isTypeSupported(",
        "svgToImage",
        "buildCompareAxisSvg",
        "buildCompareLinesSvg",
        "layoutCompareLegendItems",
        "BT_RECORD_WIDTH",
        "BT_RECORD_MIN_MS",
    ):
        assert token in script, token

    # Video legend mirrors the on-page .bt-cmp-card CSS (small fonts, flex gaps,
    # 58px right-aligned %, 5.7% left padding).
    for token in (
        "BT_LEGEND_ITEM_GAP",
        "BT_LEGEND_FLEX_GAP",
        "BT_LEGEND_PCT_MIN_W",
        "BT_LEGEND_PAD_LEFT_PCT",
        "BT_LEGEND_TITLE_SIZE",
        "BT_LEGEND_ITEM_SIZE",
    ):
        assert token in script, token

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

    # Every frame is pre-filled with the theme background, otherwise the legend
    # area below the chart is transparent→black in light mode.
    assert "ctx.fillStyle = state.bg;" in script
    assert "ctx.fillRect(0, 0, canvas.width, canvas.height);" in script

    # Backtest errors must render in a visible box: the shared yearly #pcError
    # sits inside the hidden #tab-yearly panel while the backtest tab is active.
    assert 'id="btError"' in page
    assert "function btError" in script
    assert "showError(" not in script

    # i18n keys exist in both locales.
    for key in ("record", "recordRecording", "recordUnsupported", "recordNeedRun"):
        assert key in zh_locale["backtest"], key
        assert key in en_locale["backtest"], key
    assert zh_locale["backtest"]["record"] == "录制视频"
    assert en_locale["backtest"]["record"] == "Record video"
    assert zh_locale["backtest"]["recordUnsupported"].startswith("当前浏览器不支持录制视频")
    assert en_locale["backtest"]["recordUnsupported"].startswith("Video recording is not supported")
