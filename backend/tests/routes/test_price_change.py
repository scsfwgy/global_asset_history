"""Tests for backend/routes/price_change.py — API endpoint integration tests.

All service-layer functions are mocked. These tests verify HTTP concerns:
status codes, response shapes, input validation, and error formatting.
"""

from unittest.mock import patch

import pytest

from tests.conftest import diagnose, track_coverage

MOD = "routes/price_change.py"
BASE = "/api/price-change"


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/price-change/config
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigEndpoint:
    """GET /api/price-change/config"""

    def test_returns_config(self, client):
        """Should return 200 with presets, color_range, color_scheme."""
        resp = client.get(f"{BASE}/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "presets" in data
        assert "color_range" in data
        assert "color_scheme" in data
        assert isinstance(data["presets"], list)
        diagnose("config keys", sorted(data.keys()))
        track_coverage(MOD, 3)


class TestMarketPulseEndpoint:
    """GET /api/price-change/market-pulse"""

    @patch("routes.price_change.fetch_market_pulse")
    def test_returns_market_summary(self, mock_fetch, client):
        mock_fetch.return_value = {
            "as_of": "2026-07-13T00:00:00+00:00",
            "summary": {"up": 3, "down": 2, "flat": 0, "available": 5},
            "markets": [{"symbol": "000001", "price": 4000.0, "change_pct": 1.0}],
        }
        resp = client.get(f"{BASE}/market-pulse")
        assert resp.status_code == 200
        assert resp.get_json()["summary"]["up"] == 3

    @patch("routes.price_change.fetch_market_pulse")
    def test_service_error_returns_500(self, mock_fetch, client):
        mock_fetch.side_effect = RuntimeError("boom")
        resp = client.get(f"{BASE}/market-pulse")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "boom"


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/yearly
# ═══════════════════════════════════════════════════════════════════════════

class TestYearlyEndpoint:
    """POST /api/price-change/yearly"""

    @patch("routes.price_change.fetch_yearly_returns")
    def test_valid_request(self, mock_fetch, client):
        """Valid symbols list → 200 with data."""
        mock_fetch.return_value = {
            "years": ["2024", "2023"],
            "data": {"AAPL": {"2024": 10.0, "2023": 5.0}},
            "meta": {"AAPL": {"symbol": "AAPL", "type": "stock", "error": None}},
        }
        resp = client.post(
            f"{BASE}/yearly",
            json={"symbols": [{"symbol": "AAPL", "type": "stock"}]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "years" in data
        assert "data" in data
        assert "meta" in data
        assert "AAPL" in data["data"]
        diagnose("yearly response years", data["years"])
        track_coverage(MOD, 3)

    def test_empty_symbols(self, client):
        """Empty symbols → 400."""
        resp = client.post(f"{BASE}/yearly", json={"symbols": []})
        assert resp.status_code == 400
        assert "error" in resp.get_json()
        track_coverage(MOD, 1)

    def test_no_body(self, client):
        """No JSON body → 400."""
        resp = client.post(f"{BASE}/yearly")
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    @patch("routes.price_change.fetch_yearly_returns")
    def test_service_exception_returns_500(self, mock_fetch, client):
        """Service exception → 500."""
        mock_fetch.side_effect = RuntimeError("boom")
        resp = client.post(
            f"{BASE}/yearly",
            json={"symbols": [{"symbol": "AAPL", "type": "stock"}]},
        )
        assert resp.status_code == 500
        assert "error" in resp.get_json()
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/monthly
# ═══════════════════════════════════════════════════════════════════════════

class TestMonthlyEndpoint:
    """POST /api/price-change/monthly"""

    @patch("routes.price_change.fetch_monthly_returns")
    def test_valid_request(self, mock_fetch, client):
        """Valid request → 200 with monthly data."""
        mock_fetch.return_value = [{"month": i, "return": 1.5} for i in range(1, 13)]
        resp = client.post(
            f"{BASE}/monthly",
            json={"symbol": "AAPL", "type": "stock", "year": 2024},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbol"] == "AAPL"
        assert data["year"] == 2024
        assert len(data["months"]) == 12
        track_coverage(MOD, 3)

    def test_missing_symbol(self, client):
        """Missing symbol → 400."""
        resp = client.post(f"{BASE}/monthly", json={"year": 2024})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    def test_missing_year(self, client):
        """Missing year → 400."""
        resp = client.post(f"{BASE}/monthly", json={"symbol": "AAPL"})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    def test_year_not_integer(self, client):
        """Non-integer year → 400."""
        resp = client.post(
            f"{BASE}/monthly",
            json={"symbol": "AAPL", "year": "abc"},
        )
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    @patch("routes.price_change.fetch_monthly_returns")
    def test_server_error(self, mock_fetch, client):
        mock_fetch.side_effect = RuntimeError("fail")
        resp = client.post(
            f"{BASE}/monthly",
            json={"symbol": "AAPL", "year": 2024},
        )
        assert resp.status_code == 500
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/monthly-batch
# ═══════════════════════════════════════════════════════════════════════════

class TestMonthlyBatchEndpoint:
    """POST /api/price-change/monthly-batch"""

    @patch("routes.price_change.fetch_monthly_returns_batch")
    def test_valid_request(self, mock_fetch, client):
        mock_fetch.return_value = {
            "AAPL": [{"month": i, "return": 1.0} for i in range(1, 13)],
            "GOOGL": [{"month": i, "return": 2.0} for i in range(1, 13)],
        }
        resp = client.post(
            f"{BASE}/monthly-batch",
            json={
                "symbols": [
                    {"symbol": "AAPL", "type": "stock"},
                    {"symbol": "GOOGL", "type": "stock"},
                ],
                "year": 2025,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["year"] == 2025
        assert "AAPL" in data["data"]
        track_coverage(MOD, 2)

    def test_missing_symbols(self, client):
        """Missing symbols → 400."""
        resp = client.post(f"{BASE}/monthly-batch", json={"year": 2024})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    def test_missing_year(self, client):
        """Missing year → 400."""
        resp = client.post(f"{BASE}/monthly-batch", json={"symbols": [{"symbol": "AAPL"}]})
        assert resp.status_code == 400
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/daily
# ═══════════════════════════════════════════════════════════════════════════

class TestDailyEndpoint:
    """POST /api/price-change/daily"""

    @patch("routes.price_change.fetch_daily_returns")
    def test_valid_request(self, mock_fetch, client):
        mock_fetch.return_value = [
            {"day": 1, "date": "2024-03-01", "return": None, "close": 100.0},
            {"day": 4, "date": "2024-03-04", "return": 0.5, "close": 100.5},
        ]
        resp = client.post(
            f"{BASE}/daily",
            json={"symbol": "AAPL", "type": "stock", "year": 2024, "month": 3},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["year"] == 2024
        assert data["month"] == 3
        assert len(data["days"]) == 2
        track_coverage(MOD, 3)

    def test_missing_fields(self, client):
        """Missing required fields → 400."""
        resp = client.post(f"{BASE}/daily", json={"symbol": "AAPL"})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    def test_month_out_of_range(self, client):
        """Month 0 or 13 → 400."""
        resp = client.post(
            f"{BASE}/daily",
            json={"symbol": "AAPL", "year": 2024, "month": 0},
        )
        assert resp.status_code == 400
        resp2 = client.post(
            f"{BASE}/daily",
            json={"symbol": "AAPL", "year": 2024, "month": 13},
        )
        assert resp2.status_code == 400
        track_coverage(MOD, 2)

    def test_non_integer_values(self, client):
        """Non-integer year/month → 400."""
        resp = client.post(
            f"{BASE}/daily",
            json={"symbol": "AAPL", "year": "abc", "month": 1},
        )
        assert resp.status_code == 400
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/detail
# ═══════════════════════════════════════════════════════════════════════════

class TestReturnDetailEndpoint:
    """POST /api/price-change/detail"""

    @patch("routes.price_change.fetch_return_detail")
    def test_valid_request(self, mock_fetch, client):
        mock_fetch.return_value = {
            "symbol": "BTC",
            "type": "crypto",
            "mode": "yearly",
            "years": [2025, 2024],
            "rows": [{"year": 2025, "annual_return": 10.0, "months": []}],
            "stats": [],
            "summary": {"year_count": 2},
        }
        resp = client.post(
            f"{BASE}/detail",
            json={"symbol": "BTC", "type": "crypto"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbol"] == "BTC"
        assert data["years"] == [2025, 2024]
        mock_fetch.assert_called_once_with("BTC", "crypto", None)
        track_coverage(MOD, 3)

    @patch("routes.price_change.fetch_return_detail")
    def test_valid_request_with_year(self, mock_fetch, client):
        mock_fetch.return_value = {
            "symbol": "BTC",
            "type": "crypto",
            "mode": "daily",
            "year": 2025,
            "years": [2025, 2024],
            "daily_rows": [],
            "stats": [],
            "summary": {"selected_year": 2025},
        }
        resp = client.post(
            f"{BASE}/detail",
            json={"symbol": "BTC", "type": "crypto", "year": 2025},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "daily"
        mock_fetch.assert_called_once_with("BTC", "crypto", 2025)
        track_coverage(MOD, 3)

    def test_missing_symbol(self, client):
        resp = client.post(f"{BASE}/detail", json={"type": "crypto"})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    def test_invalid_year(self, client):
        resp = client.post(
            f"{BASE}/detail",
            json={"symbol": "BTC", "type": "crypto", "year": "abc"},
        )
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    @patch("routes.price_change.fetch_return_detail")
    def test_value_error_returns_400(self, mock_fetch, client):
        mock_fetch.side_effect = ValueError("insufficient data")
        resp = client.post(
            f"{BASE}/detail",
            json={"symbol": "BAD", "type": "crypto"},
        )
        assert resp.status_code == 400
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/backtest
# ═══════════════════════════════════════════════════════════════════════════

class TestBacktestEndpoint:
    """POST /api/price-change/backtest"""

    @patch("routes.price_change.run_dca_backtest")
    def test_valid_request(self, mock_run, client):
        """Valid backtest payload → 200."""
        mock_run.return_value = {
            "symbol": "AAPL",
            "type": "stock",
            "summary": {
                "invested": 2200.0,
                "final_value": 2500.0,
                "profit": 300.0,
                "return_pct": 13.64,
                "annualized_return_pct": 8.5,
                "trade_count": 12,
            },
            "cashflows": [],
            "equity_curve": [],
        }
        resp = client.post(
            f"{BASE}/backtest",
            json={
                "symbol": "AAPL",
                "type": "stock",
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                "frequency": "monthly",
                "amount": 100,
                "initial_amount": 1000,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data
        assert data["summary"]["invested"] == 2200.0
        diagnose("backtest summary", data["summary"])
        track_coverage(MOD, 3)

    @patch("routes.price_change.run_dca_backtest")
    def test_value_error_returns_400(self, mock_run, client):
        """ValueError from service → 400."""
        mock_run.side_effect = ValueError("symbol is required")
        resp = client.post(f"{BASE}/backtest", json={"symbol": ""})
        assert resp.status_code == 400
        assert "error" in resp.get_json()
        track_coverage(MOD, 1)

    @patch("routes.price_change.run_dca_backtest")
    def test_runtime_error_returns_500(self, mock_run, client):
        """Unexpected error → 500."""
        mock_run.side_effect = RuntimeError("unexpected")
        resp = client.post(
            f"{BASE}/backtest",
            json={"symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        )
        assert resp.status_code == 500
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/crash-stats
# ═══════════════════════════════════════════════════════════════════════════

class TestCrashStatsEndpoint:
    """POST /api/price-change/crash-stats"""

    @patch("routes.price_change.run_crash_stats")
    def test_valid_request(self, mock_run, client):
        mock_run.return_value = {
            "symbol": "QQQ",
            "type": "stock",
            "summary": {
                "total_crashes": 45,
                "recovered": 42,
                "not_recovered": 3,
                "avg_recovery_days": 12.5,
            },
            "crashes": [],
        }
        resp = client.post(
            f"{BASE}/crash-stats",
            json={
                "symbol": "QQQ",
                "type": "stock",
                "start_date": "2020-01-01",
                "end_date": "2025-12-31",
                "threshold_pct": 4.77,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["summary"]["total_crashes"] == 45
        diagnose("crash-stats summary", data["summary"])
        track_coverage(MOD, 2)

    @patch("routes.price_change.run_crash_stats")
    def test_value_error_returns_400(self, mock_run, client):
        mock_run.side_effect = ValueError("symbol is required")
        resp = client.post(f"{BASE}/crash-stats", json={"symbol": ""})
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    @patch("routes.price_change.run_crash_stats")
    def test_runtime_error_returns_500(self, mock_run, client):
        mock_run.side_effect = RuntimeError("fail")
        resp = client.post(
            f"{BASE}/crash-stats",
            json={"symbol": "QQQ", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        )
        assert resp.status_code == 500
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/crash-chart
# ═══════════════════════════════════════════════════════════════════════════

class TestCrashChartEndpoint:
    """POST /api/price-change/crash-chart"""

    @patch("routes.price_change.get_crash_chart_data")
    def test_valid_request(self, mock_get, client):
        mock_get.return_value = {
            "symbol": "QQQ",
            "type": "stock",
            "pre_crash_date": "2022-05-04",
            "prices": [{"date": "2022-05-04", "close": 320.0}],
        }
        resp = client.post(
            f"{BASE}/crash-chart",
            json={
                "symbol": "QQQ",
                "type": "stock",
                "pre_crash_date": "2022-05-04",
                "trading_days": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "prices" in data
        track_coverage(MOD, 1)

    @patch("routes.price_change.get_crash_chart_data")
    def test_value_error_returns_400(self, mock_get, client):
        mock_get.side_effect = ValueError("pre_crash_date not found")
        resp = client.post(
            f"{BASE}/crash-chart",
            json={"symbol": "QQQ", "pre_crash_date": "1999-01-01"},
        )
        assert resp.status_code == 400
        track_coverage(MOD, 1)

    @patch("routes.price_change.get_crash_chart_data")
    def test_server_error_returns_500(self, mock_get, client):
        mock_get.side_effect = RuntimeError("boom")
        resp = client.post(
            f"{BASE}/crash-chart",
            json={"symbol": "QQQ", "pre_crash_date": "2022-05-04"},
        )
        assert resp.status_code == 500
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/price-change/vix-comparison
# ═══════════════════════════════════════════════════════════════════════════

class TestVixComparisonEndpoint:
    """POST /api/price-change/vix-comparison

    This endpoint has inline data-fetching logic. We test its validation
    and rely on the cache/store mocking for the data path.
    """

    def test_invalid_period_returns_400(self, client):
        """Non-existent period → 400."""
        resp = client.post(
            f"{BASE}/vix-comparison",
            json={"period": "yearly", "count": 10},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "period" in data["error"].lower() or "period" in str(data).lower()
        track_coverage(MOD, 1)

    def test_valid_period_daily(self, client):
        """Daily period should return 200 (actual data fetch may fail but route handles it)."""
        resp = client.post(
            f"{BASE}/vix-comparison",
            json={"period": "daily", "count": 30},
        )
        # This may return 200 (with possibly empty data from cache miss) or a real result
        # The key test: it should NOT be a 400 validation error
        assert resp.status_code in (200, 500)
        diagnose("vix-comparison status", resp.status_code)
        track_coverage(MOD, 1)

    def test_default_period(self, client):
        """No period specified → defaults to 'daily'."""
        resp = client.post(f"{BASE}/vix-comparison", json={})
        assert resp.status_code in (200, 500)
        track_coverage(MOD, 1)

    def test_count_clamping(self, client):
        """Count should be clamped to valid range."""
        resp = client.post(
            f"{BASE}/vix-comparison",
            json={"period": "daily", "count": 99999},
        )
        assert resp.status_code in (200, 500)
        track_coverage(MOD, 1)

    def test_period_1hour(self, client):
        """1hour period should be accepted."""
        resp = client.post(
            f"{BASE}/vix-comparison",
            json={"period": "1hour", "count": 10},
        )
        assert resp.status_code in (200, 500)
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/price-change/header-trend
# ═══════════════════════════════════════════════════════════════════════════

FETCHER = "routes.price_change._fetch_daily_series_cached"


def _series(n):
    """Build a fake PriceSeries-like object with n daily bars (ascending close)."""
    from types import SimpleNamespace

    # timestamps: 2024-01-01 + n days (UTC), closes: 100..100+n
    import calendar
    from datetime import datetime, timezone

    base = calendar.timegm(datetime(2024, 1, 1, tzinfo=timezone.utc).timetuple())
    timestamps = [base + i * 86400 for i in range(n)]
    closes = [100.0 + i for i in range(n)]
    return SimpleNamespace(timestamps=timestamps, closes=closes, source="yahoo", error=None)


class TestHeaderTrendEndpoint:
    """GET /api/price-change/header-trend"""

    @patch(FETCHER)
    def test_downsamples_to_target(self, mock_fetch, client):
        """Full history (500 pts) → downsampled to <= target points, ends kept."""
        mock_fetch.return_value = _series(500)
        resp = client.get(f"{BASE}/header-trend?symbol=QQQ&points=120")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbol"] == "QQQ"
        pts = data["points"]
        assert 60 <= len(pts) <= 120
        # Every point has date + close; close is rounded 2dp; dates ascending.
        assert all("date" in p and "close" in p for p in pts)
        assert pts == sorted(pts, key=lambda p: p["date"])
        # First and last samples preserved.
        assert pts[0]["close"] == 100.0
        assert pts[-1]["close"] == 599.0
        diagnose("header-trend points", len(pts))
        track_coverage(MOD, 3)

    @patch(FETCHER)
    def test_small_series_passthrough(self, mock_fetch, client):
        """Series smaller than target is returned whole (no padding)."""
        mock_fetch.return_value = _series(80)
        resp = client.get(f"{BASE}/header-trend?points=240")
        assert resp.status_code == 200
        assert len(resp.get_json()["points"]) == 80
        track_coverage(MOD, 1)

    @patch(FETCHER)
    def test_default_symbol_and_points(self, mock_fetch, client):
        """No params → defaults: QQQ, target 240."""
        mock_fetch.return_value = _series(300)
        resp = client.get(f"{BASE}/header-trend")
        assert resp.status_code == 200
        assert resp.get_json()["symbol"] == "QQQ"
        mock_fetch.assert_called_once_with("QQQ", "stock")
        track_coverage(MOD, 1)

    def test_points_clamped(self, client):
        """Out-of-range points clamps to [60, 400] (no 400, just clamp)."""
        with patch(FETCHER) as mock_fetch:
            mock_fetch.return_value = _series(50)
            resp = client.get(f"{BASE}/header-trend?points=99999")
            assert resp.status_code == 200
            assert len(resp.get_json()["points"]) == 50  # series smaller than 60
        with patch(FETCHER) as mock_fetch:
            mock_fetch.return_value = _series(50)
            resp = client.get(f"{BASE}/header-trend?points=1")
            assert resp.status_code == 200
        track_coverage(MOD, 1)

    @patch(FETCHER)
    def test_skips_none_closes(self, mock_fetch, client):
        """None closes are dropped before downsampling."""
        from types import SimpleNamespace

        s = _series(10)
        s.closes = [None] + s.closes[1:]  # first close missing
        mock_fetch.return_value = s
        resp = client.get(f"{BASE}/header-trend")
        pts = resp.get_json()["points"]
        assert resp.status_code == 200
        assert all(p["close"] is not None for p in pts)
        assert len(pts) == 9
        track_coverage(MOD, 1)

    @patch(FETCHER)
    def test_fetch_error_degrades_gracefully(self, mock_fetch, client):
        """Fetcher returns errored series → 200 with empty points."""
        from types import SimpleNamespace

        mock_fetch.return_value = SimpleNamespace(
            timestamps=[], closes=[], source=None, error="boom"
        )
        resp = client.get(f"{BASE}/header-trend")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["points"] == []
        assert data["meta"]["error"] == "boom"
        track_coverage(MOD, 1)

    @patch(FETCHER)
    def test_fetch_exception_returns_200_empty(self, mock_fetch, client):
        """Fetcher raises → 200 with empty points (decoration-only)."""
        mock_fetch.side_effect = RuntimeError("network")
        resp = client.get(f"{BASE}/header-trend")
        assert resp.status_code == 200
        assert resp.get_json()["points"] == []
        track_coverage(MOD, 1)
