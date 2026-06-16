"""Tests for backend/service/price_change/price_change_service.py

All external data fetching is mocked — no network calls in tests.
"""

import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from service.price_change import price_change_service as svc
from service.price_change.common import PriceSeries, empty_series
from tests.conftest import diagnose, make_daily_data, make_series, track_coverage

MOD = "price_change_service.py"


# ═══════════════════════════════════════════════════════════════════════════
# Cache tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCache:
    """Two-layer caching (L1 in-memory, L2 Redis)."""

    def setup_method(self):
        svc.clear_price_change_cache()

    def test_l1_cache_hit(self, three_year_series):
        """Fresh L1 cache entry should be returned without calling fetcher."""
        svc._set_cached_daily_series("AAPL", "stock", three_year_series)
        result = svc._get_cached_daily_series("AAPL", "stock")
        assert result is not None
        assert result.source == three_year_series.source
        assert len(result.timestamps) == len(three_year_series.timestamps)
        diagnose("L1 cache hit", f"{len(result.timestamps)} points")
        track_coverage(MOD, 3)

    def test_l1_cache_miss(self):
        """Uncached symbol should return None."""
        result = svc._get_cached_daily_series("NONEXIST", "stock")
        assert result is None
        track_coverage(MOD, 1)

    def test_l1_cache_expired(self, three_year_series):
        """Expired L1 entry should be treated as miss."""
        # Artificially age the fetched_at timestamp
        three_year_series.fetched_at = time.time() - 100000  # way past TTL
        svc._set_cached_daily_series("AAPL", "stock", three_year_series)
        # Override L2 to return None (no Redis)
        with patch.object(svc.cache_store, "cache_get", return_value=None):
            result = svc._get_cached_daily_series("AAPL", "stock")
            assert result is None
        track_coverage(MOD, 2)

    def test_clear_cache(self, three_year_series):
        """clear_price_change_cache should empty L1."""
        svc._set_cached_daily_series("AAPL", "stock", three_year_series)
        svc.clear_price_change_cache()
        assert svc._get_cached_daily_series("AAPL", "stock") is None
        track_coverage(MOD, 1)

    def test_error_ttl_shorter(self):
        """Error series should use shorter TTL (5 min vs 6 hours)."""
        ok_series = make_series(years=1)
        err_series = empty_series("test", "error msg")
        assert svc._cache_ttl(ok_series) > svc._cache_ttl(err_series)
        diagnose("OK TTL", svc._cache_ttl(ok_series))
        diagnose("Error TTL", svc._cache_ttl(err_series))
        track_coverage(MOD, 1)

    def test_serialize_roundtrip(self, three_year_series):
        """serialize → deserialize should be lossless."""
        raw = svc._serialize_series(three_year_series)
        result = svc._deserialize_series(raw)
        assert result is not None
        assert result.source == three_year_series.source
        assert result.timestamps == three_year_series.timestamps
        assert result.closes == three_year_series.closes
        track_coverage(MOD, 3)

    def test_deserialize_bad_data(self):
        """Corrupt serialized data should return None gracefully."""
        assert svc._deserialize_series("not valid json") is None
        assert svc._deserialize_series("") is None
        track_coverage(MOD, 2)

    def test_l2_cache_hit(self, three_year_series):
        """When L1 misses but L2 has data, it should warm L1 and return."""
        raw = svc._serialize_series(three_year_series)
        svc.clear_price_change_cache()
        with patch.object(svc.cache_store, "cache_get", return_value=raw):
            result = svc._get_cached_daily_series("AAPL", "stock")
            assert result is not None
            assert result.source == three_year_series.source
            # L1 should now be warmed
            result2 = svc._get_cached_daily_series("AAPL", "stock")
            assert result2 is not None
        track_coverage(MOD, 2)


# ═══════════════════════════════════════════════════════════════════════════
# fetch_yearly_returns
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchYearlyReturns:
    """Multi-symbol yearly return fetching."""

    def setup_method(self):
        svc.clear_price_change_cache()

    def test_single_stock(self, mock_fetch_daily_series, three_year_series):
        """Single stock with valid data returns yearly returns."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.fetch_yearly_returns([{"symbol": "AAPL", "type": "stock"}])
        assert "years" in result
        assert "data" in result
        assert "meta" in result
        assert "AAPL" in result["data"]
        assert result["meta"]["AAPL"]["error"] is None
        diagnose("AAPL meta", result["meta"]["AAPL"])
        track_coverage(MOD, 3)

    def test_multiple_symbols(self, mock_fetch_daily_series, three_year_series):
        """Multiple symbols fetched concurrently."""
        mock_fetch_daily_series.return_value = three_year_series
        symbols = [
            {"symbol": "AAPL", "type": "stock"},
            {"symbol": "GOOGL", "type": "stock"},
            {"symbol": "MSFT", "type": "stock"},
        ]
        result = svc.fetch_yearly_returns(symbols)
        assert len(result["data"]) == 3
        assert all(s in result["data"] for s in ["AAPL", "GOOGL", "MSFT"])
        assert mock_fetch_daily_series.call_count == 3
        diagnose("symbols fetched", list(result["data"].keys()))
        track_coverage(MOD, 2)

    def test_unknown_asset_type(self, mock_fetch_daily_series):
        """Unknown asset type returns error meta."""
        mock_fetch_daily_series.return_value = empty_series(None, "unknown asset type: futures")
        result = svc.fetch_yearly_returns([{"symbol": "CL", "type": "futures"}])
        meta = result["meta"]["CL"]
        assert meta["error"] is not None
        diagnose("unknown type error", meta["error"])
        track_coverage(MOD, 1)

    def test_empty_symbols(self):
        """Empty list returns empty data."""
        result = svc.fetch_yearly_returns([])
        assert result["data"] == {}
        assert result["meta"] == {}
        assert result["years"] == []
        track_coverage(MOD, 1)

    def test_duplicate_symbols_deduplicated(self, mock_fetch_daily_series, three_year_series):
        """Duplicate (symbol, type) pairs should be fetched once."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.fetch_yearly_returns([
            {"symbol": "AAPL", "type": "stock"},
            {"symbol": "AAPL", "type": "stock"},
        ])
        assert mock_fetch_daily_series.call_count == 1
        track_coverage(MOD, 1)

    def test_empty_symbol_string_skipped(self, mock_fetch_daily_series):
        """Symbol with empty string should be skipped."""
        result = svc.fetch_yearly_returns([{"symbol": "", "type": "stock"}])
        assert "" not in result["data"]
        track_coverage(MOD, 1)

    def test_missing_symbol_key(self, mock_fetch_daily_series):
        """Entry without 'symbol' key should be skipped gracefully."""
        result = svc.fetch_yearly_returns([{"type": "stock"}])
        assert len(result["data"]) == 0
        track_coverage(MOD, 1)

    def test_insufficient_data(self, mock_fetch_daily_series):
        """Series with <2 year-end closes → 'insufficient data' error."""
        # Create a short series (< 1 year)
        from datetime import date as dt

        from tests.conftest import _to_timestamp
        ts = [_to_timestamp(dt(2024, 1, 3)), _to_timestamp(dt(2024, 1, 4))]
        short = PriceSeries(ts, [100.0, 101.0], "test", time.time())
        mock_fetch_daily_series.return_value = short

        result = svc.fetch_yearly_returns([{"symbol": "NEW", "type": "stock"}])
        meta = result["meta"]["NEW"]
        diagnose("insufficient data meta", meta)
        # Error should indicate insufficient data
        assert meta["error"] is not None or result["data"]["NEW"] == {}
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# fetch_monthly_returns
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchMonthlyReturns:
    """Monthly return computation for a single symbol."""

    def test_active_year(self, mock_fetch_daily_series, three_year_series):
        """Year present in data → 12 months with computed returns."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.fetch_monthly_returns("AAPL", "stock", 2024)
        assert len(result) == 12
        assert all("month" in r and "return" in r for r in result)
        diagnose("monthly results sample", [(r["month"], r["return"]) for r in result[:3]])
        track_coverage(MOD, 2)

    def test_unknown_asset_type(self, mock_fetch_daily_series):
        """Unknown asset type → 12 None entries."""
        mock_fetch_daily_series.return_value = empty_series(None, "unknown")
        result = svc.fetch_monthly_returns("XXX", "futures", 2024)
        assert len(result) == 12
        assert all(r["return"] is None for r in result)
        track_coverage(MOD, 1)

    def test_error_series(self, mock_fetch_daily_series, error_series):
        """Series with fetch error → 12 None entries."""
        mock_fetch_daily_series.return_value = error_series
        result = svc.fetch_monthly_returns("AAPL", "stock", 2024)
        assert len(result) == 12
        assert all(r["return"] is None for r in result)
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# fetch_daily_returns
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchDailyReturns:
    """Daily return computation for a specific month."""

    def test_active_month(self, mock_fetch_daily_series, three_year_series):
        """Month with data → list of daily return dicts."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.fetch_daily_returns("AAPL", "stock", 2023, 6)
        assert isinstance(result, list)
        if result:
            assert all("day" in r for r in result)
            diagnose("daily count", len(result))
        track_coverage(MOD, 1)

    def test_unknown_asset_type(self, mock_fetch_daily_series):
        """Unknown type → empty list."""
        mock_fetch_daily_series.return_value = empty_series(None, "unknown")
        result = svc.fetch_daily_returns("XXX", "futures", 2024, 1)
        assert result == []
        track_coverage(MOD, 1)

    def test_error_series(self, mock_fetch_daily_series, error_series):
        """Error series → empty list."""
        mock_fetch_daily_series.return_value = error_series
        result = svc.fetch_daily_returns("AAPL", "stock", 2024, 1)
        assert result == []
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# fetch_monthly_returns_batch
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchMonthlyReturnsBatch:
    """Batch monthly return fetching."""

    def test_multiple_symbols(self, mock_fetch_daily_series, three_year_series):
        mock_fetch_daily_series.return_value = three_year_series
        symbols = [
            {"symbol": "AAPL", "type": "stock"},
            {"symbol": "GOOGL", "type": "stock"},
        ]
        result = svc.fetch_monthly_returns_batch(symbols, 2024)
        assert "AAPL" in result
        assert "GOOGL" in result
        assert len(result["AAPL"]) == 12
        track_coverage(MOD, 2)


# ═══════════════════════════════════════════════════════════════════════════
# run_dca_backtest
# ═══════════════════════════════════════════════════════════════════════════

class TestRunDcaBacktest:
    """DCA backtest execution."""

    def test_monthly_dca_with_growth(self, mock_fetch_daily_series, three_year_series):
        """Full monthly DCA backtest with upward-trending prices."""
        mock_fetch_daily_series.return_value = three_year_series
        payload = {
            "symbol": "AAPL",
            "type": "stock",
            "start_date": "2023-01-03",
            "end_date": "2024-06-28",
            "frequency": "monthly",
            "interval": 1,
            "amount": 100,
            "initial_amount": 1000,
        }
        result = svc.run_dca_backtest(payload)
        assert result["symbol"] == "AAPL"
        assert "summary" in result
        assert "cashflows" in result
        assert "equity_curve" in result
        summary = result["summary"]
        assert summary["invested"] > 0
        assert summary["final_value"] > 0
        assert summary["trade_count"] > 0
        diagnose("DCA summary", {
            "invested": summary["invested"],
            "final_value": summary["final_value"],
            "return_pct": summary["return_pct"],
            "annualized": summary["annualized_return_pct"],
            "trades": summary["trade_count"],
        })
        track_coverage(MOD, 5)

    def test_once_frequency(self, mock_fetch_daily_series, three_year_series):
        """Once frequency → single trade."""
        mock_fetch_daily_series.return_value = three_year_series
        payload = {
            "symbol": "AAPL",
            "type": "stock",
            "start_date": "2023-01-03",
            "end_date": "2024-12-31",
            "frequency": "once",
            "amount": 1000,
            "initial_amount": 0,
        }
        result = svc.run_dca_backtest(payload)
        assert result["summary"]["trade_count"] == 1  # just initial
        track_coverage(MOD, 1)

    def test_empty_symbol_raises(self):
        """Empty symbol → ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            svc.run_dca_backtest({
                "symbol": "",
                "type": "stock",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            })
        track_coverage(MOD, 1)

    def test_zero_amount_raises(self):
        """Both amount and initial_amount = 0 → ValueError."""
        with pytest.raises(ValueError, match="amount or initial_amount"):
            svc.run_dca_backtest({
                "symbol": "AAPL",
                "type": "stock",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "amount": 0,
                "initial_amount": 0,
            })
        track_coverage(MOD, 1)

    def test_end_before_start_raises(self):
        """end_date < start_date → ValueError."""
        with pytest.raises(ValueError, match="end_date"):
            svc.run_dca_backtest({
                "symbol": "AAPL",
                "start_date": "2024-12-31",
                "end_date": "2024-01-01",
                "amount": 100,
            })
        track_coverage(MOD, 1)

    def test_error_series_raises(self, mock_fetch_daily_series, error_series):
        """Series with error → ValueError."""
        mock_fetch_daily_series.return_value = error_series
        with pytest.raises(ValueError, match="network timeout"):
            svc.run_dca_backtest({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "amount": 100,
            })
        track_coverage(MOD, 1)

    def test_loss_scenario(self, mock_fetch_daily_series):
        """Declining prices → negative return."""
        # Generate a downtrend series
        from datetime import date as dt

        from tests.conftest import _to_timestamp, _trading_dates
        dates = _trading_dates(dt(2024, 1, 1), 252)
        ts = [_to_timestamp(d) for d in dates]
        price = 100.0
        closes = []
        for _ in dates:
            price *= 0.998  # ~-0.2% per day, trending down
            closes.append(round(price, 6))
        series = PriceSeries(ts, closes, "test-down", time.time())
        mock_fetch_daily_series.return_value = series

        result = svc.run_dca_backtest({
            "symbol": "AAPL",
            "type": "stock",
            "start_date": "2024-01-02",
            "end_date": "2024-12-31",
            "frequency": "monthly",
            "amount": 100,
            "initial_amount": 0,
        })
        assert result["summary"]["return_pct"] < 0
        diagnose("loss backtest", f"{result['summary']['return_pct']:.2f}%")
        track_coverage(MOD, 1)

    def test_weekly_frequency(self, mock_fetch_daily_series, three_year_series):
        """Weekly DCA should produce weekly execution points."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.run_dca_backtest({
            "symbol": "AAPL",
            "type": "stock",
            "start_date": "2023-01-02",
            "end_date": "2023-06-30",
            "frequency": "weekly",
            "interval": 1,
            "weekday": 0,  # Monday
            "amount": 100,
        })
        assert result["frequency"] == "weekly"
        diagnose("weekly trades", result["summary"]["trade_count"])
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# run_crash_stats
# ═══════════════════════════════════════════════════════════════════════════

class TestRunCrashStats:
    """Crash statistics analysis."""

    def test_with_crashes(self, mock_fetch_daily_series):
        """Data with known crashes should produce crash events."""
        from tests.conftest import make_crash_data
        ts, closes = make_crash_data()
        series = PriceSeries(ts, closes, "test-crash", time.time())
        mock_fetch_daily_series.return_value = series

        result = svc.run_crash_stats({
            "symbol": "TEST",
            "type": "stock",
            "start_date": "2022-01-01",
            "end_date": "2025-12-31",
            "threshold_pct": 3.0,
        })
        assert result["summary"]["total_crashes"] >= 2
        diagnose("crash summary", result["summary"])
        track_coverage(MOD, 2)

    def test_no_crashes(self, mock_fetch_daily_series, three_year_series):
        """Gentle uptrend → no crashes."""
        mock_fetch_daily_series.return_value = three_year_series
        result = svc.run_crash_stats({
            "symbol": "AAPL",
            "type": "stock",
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "threshold_pct": 10.0,  # high threshold
        })
        assert result["summary"]["total_crashes"] == 0
        track_coverage(MOD, 1)

    def test_validation_errors(self):
        """Various invalid inputs should raise ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            svc.run_crash_stats({
                "symbol": "",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            })
        with pytest.raises(ValueError, match="threshold"):
            svc.run_crash_stats({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "threshold_pct": 0,
            })
        with pytest.raises(ValueError, match="threshold"):
            svc.run_crash_stats({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "threshold_pct": -5,
            })
        track_coverage(MOD, 3)

    def test_error_series(self, mock_fetch_daily_series, error_series):
        """Error series → ValueError."""
        mock_fetch_daily_series.return_value = error_series
        with pytest.raises(ValueError):
            svc.run_crash_stats({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            })
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# get_crash_chart_data
# ═══════════════════════════════════════════════════════════════════════════

class TestGetCrashChartData:
    """Crash chart window data retrieval."""

    def test_valid_window(self, mock_fetch_daily_series, three_year_series):
        """Valid pre_crash_date returns a window of prices."""
        mock_fetch_daily_series.return_value = three_year_series
        # Use a date we know exists in the 3-year series
        result = svc.get_crash_chart_data({
            "symbol": "AAPL",
            "type": "stock",
            "pre_crash_date": "2023-06-15",
            "trading_days": 20,
        })
        assert "prices" in result
        assert result["pre_crash_date"] == "2023-06-15"
        diagnose("chart window size", len(result["prices"]))
        track_coverage(MOD, 2)

    def test_date_not_found(self, mock_fetch_daily_series, three_year_series):
        """Date not in data → ValueError."""
        mock_fetch_daily_series.return_value = three_year_series
        with pytest.raises(ValueError, match="not found"):
            svc.get_crash_chart_data({
                "symbol": "AAPL",
                "type": "stock",
                "pre_crash_date": "1999-01-01",
            })
        track_coverage(MOD, 1)

    def test_invalid_trading_days(self):
        """trading_days out of range → ValueError."""
        with pytest.raises(ValueError, match="trading_days"):
            svc.get_crash_chart_data({
                "symbol": "AAPL",
                "pre_crash_date": "2024-01-03",
                "trading_days": 0,
            })
        with pytest.raises(ValueError, match="trading_days"):
            svc.get_crash_chart_data({
                "symbol": "AAPL",
                "pre_crash_date": "2024-01-03",
                "trading_days": 300,
            })
        track_coverage(MOD, 2)


# ═══════════════════════════════════════════════════════════════════════════
# register_fetcher / register_daily_series_fetcher
# ═══════════════════════════════════════════════════════════════════════════

class TestFetcherRegistration:
    """Custom fetcher registration."""

    def test_register_and_use(self):
        """Register a custom fetcher and verify it's used."""
        called_with = []

        def custom_fetcher(symbol):
            called_with.append(symbol)
            return {"2023": 5.0, "2024": 10.0}

        svc.register_fetcher("custom_type", custom_fetcher)
        result = svc.fetch_yearly_returns([{"symbol": "TEST", "type": "custom_type"}])
        assert "TEST" in result["data"]
        assert called_with == ["TEST"]
        diagnose("custom fetcher called", called_with)
        track_coverage(MOD, 2)

    def test_register_daily_series_fetcher(self, three_year_series):
        """Register a daily series fetcher and verify."""
        called = []

        def custom_daily(symbol):
            called.append(symbol)
            return three_year_series

        svc.register_daily_series_fetcher("custom_daily", custom_daily)
        svc.clear_price_change_cache()
        result = svc.fetch_yearly_returns([{"symbol": "T", "type": "custom_daily"}])
        assert "T" in result["data"]
        assert len(called) == 1
        track_coverage(MOD, 2)
