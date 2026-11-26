"""Tests for clicking the header VIX badge to jump and auto-run threshold stats."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app as app_module

LOCALES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "locales"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def test_vix_badge_js_exposes_click_jump_and_accessibility(client):
    script = client.get("/js/vix-badge.js").get_data(as_text=True)
    assert "function buildThresholdUrl" in script
    assert "function navigateToThresholdStats" in script
    assert 'badge.setAttribute("role", "button")' in script
    assert 'badge.setAttribute("tabindex", "0")' in script
    assert "is-clickable" in script
    assert "window.VixThresholdJump" in script
    assert '"autorun"' in script


def test_vix_chart_js_supports_threshold_jump_and_autorun(client):
    script = client.get("/js/vix-chart.js").get_data(as_text=True)
    assert "function openFearThresholdWithParams" in script
    assert "window.VixThresholdJump = openFearThresholdWithParams;" in script
    assert 'params.get("threshold")' in script
    assert 'params.get("autorun") === "1"' in script
    assert "fetchFearThresholdStats();" in script


def test_vix_page_threshold_input_allows_decimals(client):
    html = client.get("/zh/vix").get_data(as_text=True)
    assert 'id="fearStatsThreshold" class="pc-bt-input" type="number" value="30" min="1" max="500" step="any"' in html


def test_locales_include_vix_badge_click_hint():
    for filename in ("zh-CN.json", "zh-TW.json", "en.json"):
        payload = json.loads((LOCALES_DIR / filename).read_text(encoding="utf-8"))
        assert payload["vix"]["badgeClickHint"].strip()


def test_fear_threshold_stats_accepts_decimal_vix_threshold(client):
    with patch("routes.price_change.run_fear_threshold_stats") as mock_run:
        mock_run.return_value = {
            "index": "VIX",
            "asset": "SPY",
            "threshold": 18.42,
            "start_date": "2000-01-01",
            "end_date": "2026-11-26",
            "event_count": 0,
            "summary": {},
            "events": [],
            "meta": {},
        }
        resp = client.post(
            "/api/price-change/fear-threshold-stats",
            json={
                "index": "VIX",
                "threshold": 18.42,
                "start_date": "2000-01-01",
                "end_date": "2026-11-26",
            },
        )
    assert resp.status_code == 200
    assert resp.get_json()["threshold"] == 18.42
    mock_run.assert_called_once()


def test_vix_chart_js_redirects_when_overview_panel_was_route_pruned(client):
    script = client.get("/js/vix-chart.js").get_data(as_text=True)
    assert "if (target === \"overview\" && !activeOverview)" in script
    assert "window.location.assign(overviewPath);" in script
    assert "activeOverview = zhOverview || enOverview;" in script
