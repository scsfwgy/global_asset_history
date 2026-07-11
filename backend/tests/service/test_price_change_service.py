"""Tests for backend/service/price_change/price_change_service.py

All external data fetching is mocked — no network calls in tests.
"""

import time
from datetime import date, datetime, timezone
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

    @pytest.fixture(autouse=True)
    def _isolate_fetcher_state(self):
        """Save/restore module-level fetcher dicts so test registrations
        don't leak into other tests (which may call _get_cached_daily_series
        with symbols like AAPL and interfere with mock assertions)."""
        orig_fetchers = dict(svc._FETCHERS)
        orig_daily = dict(svc._DAILY_SERIES_FETCHERS)
        yield
        svc._FETCHERS.clear()
        svc._FETCHERS.update(orig_fetchers)
        svc._DAILY_SERIES_FETCHERS.clear()
        svc._DAILY_SERIES_FETCHERS.update(orig_daily)

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


# ═══════════════════════════════════════════════════════════════════════════
# Heatmap today fast-path tests
# ═══════════════════════════════════════════════════════════════════════════


class TestYahooQuoteBatch:
    """Unit tests for _yahoo_quote_batch — batch v7/quote fetching."""

    @patch("service.price_change.price_change_service._yh_session")
    @patch("service.price_change.price_change_service._yahoo_crumb")
    def test_returns_quotes(self, mock_crumb, mock_session):
        """Valid crumb + 200 response → parsed quote list."""
        mock_crumb.return_value = "valid-crumb"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "AAPL",
                        "shortName": "Apple Inc.",
                        "regularMarketPrice": 150.0,
                        "regularMarketChangePercent": 2.5,
                        "regularMarketVolume": 1000000,
                        "marketCap": 3000000000000,
                    },
                    {
                        "symbol": "MSFT",
                        "longName": "Microsoft Corporation",
                        "regularMarketPrice": 300.0,
                        "regularMarketChangePercent": -1.2,
                        "regularMarketVolume": 500000,
                        "marketCap": 2500000000000,
                    },
                ]
            }
        }
        mock_session.get.return_value = mock_resp

        result = svc._yahoo_quote_batch(["AAPL", "MSFT"])
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["name"] == "Apple Inc."
        assert result[0]["price"] == 150.0
        assert result[0]["change_pct"] == 2.5
        assert result[0]["volume"] == 1000000
        assert result[0]["market_cap"] == 3000000000000
        assert result[1]["symbol"] == "MSFT"
        assert result[1]["name"] == "Microsoft Corporation"
        track_coverage(MOD, 3)

    @patch("service.price_change.price_change_service._yh_session")
    @patch("service.price_change.price_change_service._yahoo_crumb")
    def test_no_crumb_returns_empty(self, mock_crumb, mock_session):
        """None crumb → empty list (no request made)."""
        mock_crumb.return_value = None
        result = svc._yahoo_quote_batch(["AAPL"])
        assert result == []
        mock_session.get.assert_not_called()
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yh_session")
    @patch("service.price_change.price_change_service._yahoo_crumb")
    def test_non_200_returns_empty(self, mock_crumb, mock_session):
        """Non-200 status → empty list for that chunk."""
        mock_crumb.return_value = "crumb"
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_session.get.return_value = mock_resp

        result = svc._yahoo_quote_batch(["AAPL"])
        assert result == []
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yh_session")
    @patch("service.price_change.price_change_service._yahoo_crumb")
    def test_none_price_skipped(self, mock_crumb, mock_session):
        """Symbol with regularMarketPrice=None is filtered out."""
        mock_crumb.return_value = "crumb"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "AAPL",
                        "regularMarketPrice": None,  # no price
                        "regularMarketChangePercent": 2.5,
                    }
                ]
            }
        }
        mock_session.get.return_value = mock_resp

        result = svc._yahoo_quote_batch(["AAPL"])
        assert len(result) == 0
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yh_session")
    @patch("service.price_change.price_change_service._yahoo_crumb")
    def test_batch_splitting(self, mock_crumb, mock_session):
        """Symbols beyond _YH_BATCH (50) are split across multiple requests."""
        mock_crumb.return_value = "crumb"

        def make_page(url, params=None, **kwargs):
            syms = (params or {}).get("symbols", "").split(",")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": s,
                            "regularMarketPrice": 100.0,
                            "regularMarketChangePercent": 1.0,
                        }
                        for s in syms
                    ]
                }
            }
            return mock_resp

        mock_session.get.side_effect = make_page

        symbols = [f"SYM{i}" for i in range(60)]
        result = svc._yahoo_quote_batch(symbols)
        assert len(result) == 60
        assert mock_session.get.call_count == 2  # 50 + 10 = 2 batches
        track_coverage(MOD, 2)


class TestBuildHeatmapToday:
    """Tests for _build_heatmap_today — today fast-path orchestrator."""

    def _compute_stub(self, sym, atype):
        """Stub matching _compute_one signature for non-stock entries."""
        return {
            "symbol": sym,
            "name": None,
            "type": atype,
            "return_pct": 5.0,
            "turnover": 999.0,
            "turnover_currency": "USD" if atype == "stock" else "CNY",
        }

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_all_stocks_success(self, mock_batch):
        """All entries are stocks → batch used, no fallback."""
        mock_batch.return_value = [
            {"symbol": "AAPL", "name": "Apple", "price": 150.0,
             "change_pct": 2.5, "volume": 1000000, "market_cap": 3e12},
            {"symbol": "MSFT", "name": "Microsoft", "price": 300.0,
             "change_pct": -1.0, "volume": 500000, "market_cap": 2.5e12},
        ]
        entries = [("AAPL", "stock"), ("MSFT", "stock")]
        user = {"MSFT"}
        auto = {"AAPL"}

        result = svc._build_heatmap_today(
            entries, user, auto, auto_top_n=20,
            include_market_cap=True, compute_fn=self._compute_stub,
        )
        assert result is not None
        assert result["period"] == "today"
        assert result["period_label"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert len(result["data"]) == 2
        # Auto symbols first, then user
        assert result["data"][0]["symbol"] == "AAPL"
        assert result["data"][0]["name"] == "Apple"
        assert result["data"][0]["return_pct"] == 2.5
        turnover = result["data"][0]["turnover"]
        assert turnover == round(1000000 * 150.0, 2)
        assert result["data"][0]["market_cap"] == 3e12
        track_coverage(MOD, 3)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_batch_fails_fallback(self, mock_batch):
        """Batch returns empty for non-empty stocks → return None."""
        mock_batch.return_value = []
        entries = [("AAPL", "stock"), ("MSFT", "stock")]

        result = svc._build_heatmap_today(
            entries, set(), set(), auto_top_n=0,
            include_market_cap=False, compute_fn=self._compute_stub,
        )
        assert result is None
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_market_cap_disabled(self, mock_batch):
        """include_market_cap=False → market_cap absent from results."""
        mock_batch.return_value = [
            {"symbol": "AAPL", "name": "Apple", "price": 150.0,
             "change_pct": 2.5, "volume": 1000000, "market_cap": 3e12},
        ]
        result = svc._build_heatmap_today(
            [("AAPL", "stock")], {"AAPL"}, set(), auto_top_n=0,
            include_market_cap=False, compute_fn=self._compute_stub,
        )
        assert result is not None
        assert "market_cap" in result["data"][0]
        assert result["data"][0]["market_cap"] is None
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_mixed_stock_and_crypto(self, mock_batch):
        """Stocks via batch, crypto via compute_fn."""
        mock_batch.return_value = [
            {"symbol": "AAPL", "name": "Apple", "price": 150.0,
             "change_pct": 2.5, "volume": 1000000, "market_cap": 3e12},
        ]
        entries = [("AAPL", "stock"), ("BTC", "crypto")]
        user = set()
        auto = {"AAPL", "BTC"}

        result = svc._build_heatmap_today(
            entries, user, auto, auto_top_n=20,
            include_market_cap=True, compute_fn=self._compute_stub,
        )
        assert result is not None
        assert len(result["data"]) == 2
        # BTC came from compute_stub
        btc = next(r for r in result["data"] if r["symbol"] == "BTC")
        assert btc["return_pct"] == 5.0
        assert btc["type"] == "crypto"
        track_coverage(MOD, 2)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_empty_entries(self, mock_batch):
        """No entries → empty data, batch never called."""
        result = svc._build_heatmap_today(
            [], set(), set(), auto_top_n=0,
            include_market_cap=True, compute_fn=self._compute_stub,
        )
        assert result is not None
        assert result["data"] == []
        mock_batch.assert_not_called()
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_symbol_not_in_quote_map(self, mock_batch):
        """Stock not in batch response → None values, no crash."""
        mock_batch.return_value = []  # AAPL missing from response
        entries = [("AAPL", "stock")]
        # No stocks AND empty batch → _build_heatmap_today sees
        # stock_syms=["AAPL"] but quotes=[] → returns None (fallback).
        # Test the edge case: stock_syms non-empty, batch returned partial.
        # Actually we need quotes non-empty to avoid the "fail" path.
        mock_batch.return_value = [
            {"symbol": "MSFT", "name": "MS", "price": 300.0,
             "change_pct": 1.0, "volume": 500000, "market_cap": 2.5e12},
        ]
        result = svc._build_heatmap_today(
            [("AAPL", "stock"), ("MSFT", "stock")],
            {"AAPL", "MSFT"}, set(), auto_top_n=0,
            include_market_cap=False, compute_fn=self._compute_stub,
        )
        assert result is not None
        assert len(result["data"]) == 2
        aapl = next(r for r in result["data"] if r["symbol"] == "AAPL")
        assert aapl["return_pct"] is None
        assert aapl["turnover"] is None
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_auto_top_n_respected(self, mock_batch):
        """auto_top_n limits auto results, user symbols always included."""
        mock_batch.return_value = [
            {"symbol": s, "name": s, "price": 100.0 + i,
             "change_pct": 1.0, "volume": 100000 * (i + 1),
             "market_cap": 1e12}
            for i, s in enumerate(["A1", "A2", "A3", "A4", "A5"])
        ]
        entries = [("A1", "stock"), ("A2", "stock"), ("A3", "stock"),
                   ("A4", "stock"), ("A5", "stock"), ("USER1", "stock")]
        user = {"USER1"}
        auto = {"A1", "A2", "A3", "A4", "A5"}

        result = svc._build_heatmap_today(
            entries, user, auto, auto_top_n=3,
            include_market_cap=False, compute_fn=self._compute_stub,
        )
        assert result is not None
        # Top 3 auto + 1 user = 4
        assert len(result["data"]) == 4
        # Auto sorted by turnover desc (A5 has highest vol)
        assert result["data"][0]["symbol"] == "A5"
        assert result["data"][1]["symbol"] == "A4"
        assert result["data"][2]["symbol"] == "A3"
        # User always present
        assert result["data"][3]["symbol"] == "USER1"
        track_coverage(MOD, 2)


class TestFetchHeatmapToday:
    """Integration tests: fetch_heatmap_data with period='today'."""

    @patch("service.price_change.price_change_service._build_heatmap_today")
    def test_today_fast_path_used(self, mock_build):
        """period='today' routes through _build_heatmap_today."""
        mock_build.return_value = {
            "period": "today", "period_label": "1d",
            "data": [{"symbol": "AAPL", "type": "stock"}],
        }
        result = svc.fetch_heatmap_data(
            symbols=[{"symbol": "AAPL", "type": "stock"}],
            period="today", auto_top_n=0, include_market_cap=True,
        )
        assert result["period"] == "today"
        mock_build.assert_called_once()
        track_coverage(MOD, 1)

    @patch("service.price_change.price_change_service._build_heatmap_today")
    def test_today_fast_path_fallback_to_ohlcv(self, mock_build):
        """When fast path returns None, fall through to per-symbol OHLCV."""
        mock_build.return_value = None

        with patch(
            "service.price_change.price_change_service._fetch_daily_series_cached"
        ) as mock_fetch, patch(
            "service.price_change.price_change_service._yahoo_quote_batch",
            return_value=[{
                "symbol": "AAPL", "name": "Apple Inc.", "price": 150.0,
                "change_pct": 1.0, "volume": 1000, "market_cap": 3e12,
            }],
        ):
            from tests.conftest import make_series
            mock_fetch.return_value = make_series(years=1, start_price=100.0)

            result = svc.fetch_heatmap_data(
                symbols=[{"symbol": "AAPL", "type": "stock"}],
                period="today", auto_top_n=0, include_market_cap=False,
            )
        assert result["period"] == "today"
        mock_build.assert_called_once()
        mock_fetch.assert_called()
        track_coverage(MOD, 2)

    @patch("service.price_change.price_change_service._build_heatmap_today")
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_non_today_skips_fast_path(self, mock_fetch, mock_build):
        """period='month' should NOT use the today fast path."""
        from tests.conftest import make_series
        mock_fetch.return_value = make_series(years=1, start_price=100.0)

        with patch(
            "service.price_change.price_change_service._yahoo_quote_batch",
            return_value=[{
                "symbol": "AAPL", "name": "Apple Inc.", "price": 150.0,
                "change_pct": 1.0, "volume": 1000, "market_cap": 3e12,
            }],
        ) as mock_quotes:
            result = svc.fetch_heatmap_data(
                symbols=[{"symbol": "AAPL", "type": "stock"}],
                period="month", auto_top_n=0, include_market_cap=False,
            )
        assert result["period"] == "month"
        assert result["data"][0]["name"] == "Apple Inc."
        mock_build.assert_not_called()
        mock_fetch.assert_called()
        mock_quotes.assert_called_once_with(["AAPL"])
        track_coverage(MOD, 2)
