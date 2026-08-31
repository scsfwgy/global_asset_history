"""Tests for backend/service/price_change/price_change_service.py

All external data fetching is mocked — no network calls in tests.
"""

import time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from service.price_change import price_change_service as svc
from service.price_change.common import PriceSeries, empty_series
from tests.conftest import diagnose, make_daily_data, make_series, track_coverage

MOD = "price_change_service.py"


class TestSearchAssetSymbols:
    """Company-name and symbol lookup for reusable autocomplete controls."""

    def setup_method(self):
        with svc._symbol_search_lock:
            svc._symbol_search_cache.clear()

    @patch.object(svc._em_session, "get")
    def test_filters_east_money_results_for_selected_market(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "QuotationCodeTable": {"Data": [
                {
                    "UnifiedCode": "AAPL",
                    "Name": "苹果",
                    "JYS": "NASDAQ",
                    "Classify": "UsStock",
                    "TypeUS": "1",
                },
                {
                    "UnifiedCode": "AAPL22",
                    "Name": "Apple Notes",
                    "JYS": "NASDAQ",
                    "Classify": "UsStock",
                    "TypeUS": "6",
                },
                {
                    "UnifiedCode": "09988",
                    "Name": "阿里巴巴-W",
                    "JYS": "HK",
                    "Classify": "HK",
                    "TypeUS": "3",
                },
            ]}
        }

        result = svc.search_asset_symbols("Apple", "stock")

        assert result == [{
            "symbol": "AAPL",
            "name": "苹果",
            "type": "stock",
            "exchange": "NASDAQ",
        }]
        assert mock_get.call_args.kwargs["params"]["input"] == "Apple"

    @patch.object(svc._em_session, "get")
    def test_a_share_search_uses_human_readable_exchange_name(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "QuotationCodeTable": {"Data": [{
                "UnifiedCode": "600519",
                "Name": "贵州茅台",
                "JYS": "2",
                "SecurityTypeName": "沪A",
                "Classify": "AStock",
            }]}
        }

        result = svc.search_asset_symbols("贵州茅台", "cn_stock")

        assert result[0]["exchange"] == "沪A"

    @patch.object(svc._em_session, "get")
    def test_a_share_etf_search_accepts_fund_classification(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "QuotationCodeTable": {"Data": [{
                "UnifiedCode": "159941",
                "Name": "纳指ETF广发",
                "JYS": "10",
                "SecurityTypeName": "基金",
                "Classify": "Fund",
            }]}
        }

        result = svc.search_asset_symbols("159941", "cn_stock")

        assert result[0]["symbol"] == "159941"
        assert result[0]["name"] == "纳指ETF广发"
        assert result[0]["exchange"] == "基金"

    @patch.object(svc, "_yahoo_crumb", return_value=None)
    @patch.object(svc._yh_session, "get")
    def test_global_search_uses_yahoo_compatible_symbols(self, mock_get, _mock_crumb):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"quotes": [{
            "symbol": "7203.T",
            "longname": "Toyota Motor Corporation",
            "quoteType": "EQUITY",
            "exchDisp": "Tokyo",
        }]}

        result = svc.search_asset_symbols("Toyota", "global_stock")

        assert result[0] == {
            "symbol": "7203.T",
            "name": "Toyota Motor Corporation",
            "type": "global_stock",
            "exchange": "Tokyo",
        }


class TestFetchPriceHistory:
    """Date filtering and OHLCV period aggregation for JSON downloads."""

    @staticmethod
    def _series():
        timestamps = [
            int(datetime(2024, 1, day, 12, tzinfo=timezone.utc).timestamp())
            for day in (1, 2, 8)
        ]
        return PriceSeries(
            timestamps=timestamps,
            closes=[11.0, 12.0, 13.0],
            source="test-source",
            fetched_at=timestamps[-1],
            opens=[10.0, 11.0, 12.0],
            highs=[12.0, 13.0, 14.0],
            lows=[9.0, 10.0, 11.0],
            volumes=[100.0, 200.0, 300.0],
        )

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_daily_filters_requested_date_range(self, mock_fetch):
        mock_fetch.return_value = self._series()
        result = svc.fetch_price_history("btc", "crypto", "daily", "2024-01-02", "2024-01-08")
        assert result["symbol"] == "BTC"
        assert result["count"] == 2
        assert [row["date"] for row in result["data"]] == ["2024-01-02", "2024-01-08"]
        assert result["data"][0]["volume"] == 200.0

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_global_stock_reuses_stock_fetcher_with_local_market_metadata(self, mock_fetch):
        mock_fetch.return_value = self._series()

        result = svc.fetch_price_history(
            "2330.tw", "global_stock", "daily", "2024-01-01", "2024-01-08"
        )

        assert result["symbol"] == "2330.TW"
        assert result["type"] == "global_stock"
        assert result["currency"] == "TWD"
        assert result["market"] == "TW"
        assert result["count"] == 3
        mock_fetch.assert_called_once_with("2330.TW", "stock")

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_weekly_aggregates_ohlcv(self, mock_fetch):
        mock_fetch.return_value = self._series()
        result = svc.fetch_price_history("BTC", "crypto", "weekly", "2024-01-01", "2024-01-31")
        assert result["count"] == 2
        first = result["data"][0]
        assert first == {
            "date": "2024-01-01",
            "period_end": "2024-01-02",
            "open": 10.0,
            "high": 13.0,
            "low": 9.0,
            "close": 12.0,
            "volume": 300.0,
        }

    @patch("service.price_change.price_change_service.fetch_intraday_series")
    def test_intraday_returns_timestamped_bars(self, mock_fetch):
        timestamp = int(datetime(2024, 1, 2, 3, 0, tzinfo=timezone.utc).timestamp())
        mock_fetch.return_value = PriceSeries(
            timestamps=[timestamp], closes=[101.0], source="binance", fetched_at=timestamp,
            opens=[100.0], highs=[102.0], lows=[99.0], volumes=[1234.0],
        )
        result = svc.fetch_price_history("btc", "crypto", "1h", "2024-01-01", "2024-01-03")
        assert result["period"] == "1h"
        assert result["data"] == [{
            "date": "2024-01-02T03:00:00Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1234.0,
        }]
        mock_fetch.assert_called_once_with("BTC", "crypto", "1h", date(2024, 1, 1), date(2024, 1, 3))

    @patch("service.price_change.price_change_service.fetch_intraday_series")
    def test_intraday_rejects_excessive_date_range(self, mock_fetch):
        with pytest.raises(ValueError, match="maximum date range of 7 days"):
            svc.fetch_price_history("BTC", "crypto", "1m", "2024-01-01", "2024-01-08")
        mock_fetch.assert_not_called()

    def test_rejects_invalid_period_and_date_range(self):
        with pytest.raises(ValueError, match="period must be"):
            svc.fetch_price_history("BTC", "crypto", "hourly", "2024-01-01", "2024-01-02")
        with pytest.raises(ValueError, match="on or before"):
            svc.fetch_price_history("BTC", "crypto", "daily", "2024-01-03", "2024-01-02")


class TestFetchReturnDetail:
    """Return-detail chart data uses compounded period returns."""

    def setup_method(self):
        # fetch_return_detail falls back to the shared symbol-search for the
        # asset name; keep these tests offline by defaulting it to no hits.
        self._search_patch = patch.object(svc, "search_asset_symbols", return_value=[])
        self._search_patch.start()

    def teardown_method(self):
        self._search_patch.stop()

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_selected_year_includes_monthly_returns(self, mock_fetch):
        series = make_series(years=2)
        mock_fetch.return_value = series
        selected_year = max(int(year) for year in svc._compute_yearly_returns(
            series.timestamps, series.closes
        ))

        result = svc.fetch_return_detail("btc", "crypto", selected_year)

        assert result["mode"] == "daily"
        expected_returns = svc._compute_monthly_returns(
            series.timestamps, series.closes, selected_year
        )
        assert [
            {"month": item["month"], "return": item["return"]}
            for item in result["monthly_returns"]
        ] == expected_returns
        assert all("max_daily_gain" in item for item in result["monthly_returns"])
        assert all("max_daily_loss" in item for item in result["monthly_returns"])
        assert [item["month"] for item in result["monthly_returns"]] == list(range(1, 13))

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_yearly_and_monthly_periods_include_daily_extremes(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 4, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
        ]
        mock_fetch.return_value = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[100.0, 110.0, 99.0, 108.9, 87.12, 120.0],
            source="test",
            fetched_at=dates[-1].timestamp(),
        )

        yearly = svc.fetch_return_detail("BTC", "crypto")
        row = yearly["rows"][0]
        assert row["annual_return"] == 20.0
        assert row["max_daily_gain"] == {"date": "2024-12-31", "return": 37.74}
        assert row["max_daily_loss"] == {"date": "2024-02-01", "return": -20.0}
        january = row["months"][0]
        assert january["max_daily_gain"] == {"date": "2024-01-02", "return": 10.0}
        assert january["max_daily_loss"] == {"date": "2024-01-03", "return": -10.0}

        selected = svc.fetch_return_detail("BTC", "crypto", 2024)
        february = selected["monthly_returns"][1]
        assert february["max_daily_gain"] is None
        assert february["max_daily_loss"] == {"date": "2024-02-01", "return": -20.0}

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_stock_detail_includes_combined_history_table(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
        ]
        mock_fetch.return_value = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[100.0, 120.0, 90.0, 125.0],
            source="test",
            fetched_at=dates[-1].timestamp(),
            raw_closes=[200.0, 210.0, 180.0, 220.0],
            dividends=[
                {
                    "timestamp": int(datetime(2024, 3, 1, tzinfo=timezone.utc).timestamp()),
                    "amount": 0.25,
                },
                {
                    "timestamp": int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()),
                    "amount": 0.3,
                },
            ],
        )

        result = svc.fetch_return_detail("AAPL", "stock")

        row = next(
            row for row in result["stock_tables"]["rows"] if row["year"] == 2024
        )
        assert row == {
            "year": 2024,
            "annual_return": 10.0,
            "max_drawdown": -14.29,
            "max_runup": 22.22,
            "payment_count": 2,
            "dividend_payments": [
                {"date": "2024-03-01", "amount": 0.25},
                {"date": "2024-06-01", "amount": 0.3},
            ],
            "total_dividend_per_share": 0.55,
            "dividend_yield_basis_price": 200.0,
        }
        assert result["stock_tables"]["return_basis"] == "raw_close"
        assert result["stock_tables"]["dividend_yield_basis"] == "previous_year_end_close"
        assert result["overview"]["latest_price"] == 220.0
        assert result["overview"]["latest_adjusted_close"] == 125.0
        assert result["overview"]["latest_date"] == "2024-12-31"
        assert result["overview"]["price_basis"] == "raw_close"
        assert result["overview"]["ytd_return"] == 25.0
        assert result["overview"]["all_time_return"] == 25.0
        assert result["overview"]["all_time_adjusted_return"] == 25.0
        assert result["overview"]["all_time_unadjusted_return"] == 10.0
        assert result["overview"]["all_time_unadjusted_first_date"] == "2023-12-29"
        assert result["overview"]["all_time_unadjusted_latest_date"] == "2024-12-31"
        assert result["fundamentals"]["available"] is True
        assert result["fundamentals"]["fifty_two_week_high"] == 220.0
        assert result["fundamentals"]["fifty_two_week_low"] == 180.0
        assert result["fundamentals"]["dividend_per_share_ttm"] == 0.55
        assert result["fundamentals"]["dividend_yield"] == 0.25

        selected = svc.fetch_return_detail("AAPL", "stock", 2024)
        assert selected["stock_tables"] is not None
        selected = svc.fetch_return_detail(
            "AAPL", "stock", 2024, include_stock_history=False
        )
        assert selected["stock_tables"] is None

        hk_result = svc.fetch_return_detail("700", "hk_stock")
        assert hk_result["symbol"] == "0700.HK"
        assert hk_result["type"] == "hk_stock"
        assert hk_result["fundamentals"]["currency"] == "HKD"
        assert hk_result["stock_tables"]["dividend_unit"] == "HKD/share"
        mock_fetch.assert_called_with("0700.HK", "hk_stock")

        global_result = svc.fetch_return_detail("2330.tw", "global_stock")
        assert global_result["symbol"] == "2330.TW"
        assert global_result["type"] == "global_stock"
        assert global_result["fundamentals"]["currency"] == "TWD"
        assert global_result["stock_tables"]["dividend_unit"] == "TWD/share"
        mock_fetch.assert_called_with("2330.TW", "global_stock")

    def test_detail_period_returns_drawdowns_and_distribution_stats(self):
        points = [
            (date(2020, 1, 1), 100.0),
            (date(2021, 1, 1), 110.0),
            (date(2022, 1, 1), 121.0),
            (date(2023, 1, 1), 133.1),
        ]
        assert svc._detail_period_return(points, 1) == pytest.approx(10.0, abs=0.02)
        assert svc._detail_period_return(points, 3, annualized=True) == pytest.approx(
            10.0, abs=0.02
        )
        assert svc._detail_all_time_return(points) == pytest.approx(33.1)
        assert svc._detail_all_time_return(points[:1]) is None

        drawdown = svc._detail_drawdown_summary([
            (date(2024, 1, 2), 100.0),
            (date(2024, 2, 1), 120.0),
            (date(2024, 3, 1), 60.0),
            (date(2024, 4, 1), 90.0),
            (date(2024, 5, 1), 120.0),
        ])
        assert drawdown == {
            "current_drawdown": 0.0,
            "all_time_high_date": "2024-05-01",
            "max_drawdown": -50.0,
            "max_drawdown_peak_date": "2024-02-01",
            "max_drawdown_trough_date": "2024-03-01",
            "max_drawdown_recovery_date": "2024-05-01",
            "max_drawdown_recovery_trading_days": 2,
        }

        stats = svc._build_monthly_stats({1: [10.0, -5.0, 0.0]})
        assert stats[0]["win_rate"] == 33.3
        assert stats[0]["count"] == 3
        assert svc._row_stats([10.0, -5.0, None]) == {
            "avg": 2.5,
            "median": 2.5,
            "win_rate": 50.0,
            "count": 2,
        }

    def test_detail_quality_includes_downside_and_rolling_distribution(self):
        start = datetime(2023, 1, 1, 12, tzinfo=timezone.utc)
        dates = [
            start + timedelta(days=index)
            for index in range(426)
        ]
        closes = [100.0]
        for index in range(1, len(dates)):
            daily_return = 0.01 if index % 2 else -0.005
            closes.append(closes[-1] * (1 + daily_return))
        series = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=closes,
            source="test",
            fetched_at=dates[-1].timestamp(),
        )

        quality = svc._build_detail_quality(series, "crypto")

        assert quality["daily_win_rate"] == 50.1
        assert quality["daily_observations"] == 425
        assert quality["downside_volatility_1y"] == pytest.approx(6.76, abs=0.02)
        assert quality["sortino_ratio_1y"] > 2
        assert quality["best_day_1y"]["return"] == 1.0
        assert quality["worst_day_1y"]["return"] == -0.5
        assert quality["rolling_1y_win_rate"] == 100.0
        assert quality["rolling_1y_median"] > 0
        assert quality["rolling_1y_observations"] == 71
        assert quality["rolling_1y_best"]["start_date"] == "2023-01-01"
        assert quality["return_basis"] == "adjusted_close"
        assert quality["sortino_target_return"] == 0

    @patch("service.price_change.price_change_service._fetch_detail_fundamentals")
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_stock_detail_includes_quality_and_fundamental_snapshot(
        self,
        mock_fetch,
        mock_fundamentals,
    ):
        series = make_series(years=2)
        series.source = "yahoo/yfinance"
        mock_fetch.return_value = series
        mock_fundamentals.return_value = {
            "available": True,
            "market_cap": 3_000_000_000_000,
        }

        result = svc.fetch_return_detail("AAPL", "stock")

        assert result["quality"]["daily_observations"] > 0
        assert result["fundamentals"]["market_cap"] == 3_000_000_000_000
        mock_fundamentals.assert_called_once_with("AAPL")

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_non_stock_detail_omits_stock_history_tables(self, mock_fetch):
        mock_fetch.return_value = make_series(years=2)

        result = svc.fetch_return_detail("BTC", "crypto")

        assert result["stock_tables"] is None

    def test_yearly_drawdown_resets_peak_each_calendar_year(self):
        dates = [
            datetime(2023, 1, 2, tzinfo=timezone.utc),
            datetime(2023, 6, 1, tzinfo=timezone.utc),
            datetime(2023, 12, 29, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
        ]

        rows = svc._compute_yearly_drawdowns(
            [int(item.timestamp()) for item in dates],
            [200.0, 100.0, 150.0, 120.0, 108.0],
        )

        assert rows == [
            {
                "year": 2024,
                "max_drawdown": -10.0,
                "peak_date": "2024-01-02",
                "trough_date": "2024-02-01",
            },
            {
                "year": 2023,
                "max_drawdown": -50.0,
                "peak_date": "2023-01-02",
                "trough_date": "2023-06-01",
            },
        ]

    def test_period_drawdown_includes_previous_close_as_boundary(self):
        dates = [
            datetime(2023, 12, 29, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            datetime(2024, 1, 31, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 29, tzinfo=timezone.utc),
        ]

        yearly = svc._compute_period_drawdowns(
            [int(item.timestamp()) for item in dates],
            [100.0, 80.0, 90.0, 72.0, 81.0],
            period="year",
            include_previous_close=True,
        )
        monthly = svc._compute_period_drawdowns(
            [int(item.timestamp()) for item in dates],
            [100.0, 80.0, 90.0, 72.0, 81.0],
            period="month",
            include_previous_close=True,
        )

        assert yearly[0] == {
            "year": 2024,
            "max_drawdown": -28.0,
            "peak_date": "2023-12-29",
            "trough_date": "2024-02-01",
        }
        assert monthly[:2] == [
            {
                "year": 2024,
                "month": 2,
                "max_drawdown": -20.0,
                "peak_date": "2024-01-31",
                "trough_date": "2024-02-01",
            },
            {
                "year": 2024,
                "month": 1,
                "max_drawdown": -20.0,
                "peak_date": "2023-12-29",
                "trough_date": "2024-01-02",
            },
        ]

    def test_yearly_runup_resets_trough_each_calendar_year(self):
        dates = [
            datetime(2023, 1, 2, tzinfo=timezone.utc),
            datetime(2023, 6, 1, tzinfo=timezone.utc),
            datetime(2023, 12, 29, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
        ]

        rows = svc._compute_yearly_runups(
            [int(item.timestamp()) for item in dates],
            [100.0, 80.0, 120.0, 200.0, 150.0, 180.0],
        )

        assert rows == [
            {
                "year": 2024,
                "max_runup": 20.0,
                "trough_date": "2024-02-01",
                "peak_date": "2024-03-01",
            },
            {
                "year": 2023,
                "max_runup": 50.0,
                "trough_date": "2023-06-01",
                "peak_date": "2023-12-29",
            },
        ]

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_daily_extreme_ties_keep_first_occurrence(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 4, 12, tzinfo=timezone.utc),
        ]
        mock_fetch.return_value = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[100.0, 110.0, 99.0, 108.9],
            source="test",
            fetched_at=dates[-1].timestamp(),
        )

        result = svc.fetch_return_detail("BTC", "crypto")
        january = result["rows"][0]["months"][0]
        assert january["max_daily_gain"] == {"date": "2024-01-02", "return": 10.0}
        assert january["max_daily_loss"] == {"date": "2024-01-03", "return": -10.0}

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_candles_use_adjusted_ohlc_and_previous_period_close(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 31, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 29, 12, tzinfo=timezone.utc),
        ]
        mock_fetch.return_value = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[50.0, 55.0, 60.0, 57.0, 63.0],
            raw_closes=[100.0, 110.0, 120.0, 114.0, 126.0],
            opens=[98.0, 108.0, 114.0, 120.0, 116.0],
            highs=[102.0, 112.0, 124.0, 120.0, 130.0],
            lows=[97.0, 106.0, 106.0, 112.0, 110.0],
            source="test",
            fetched_at=dates[-1].timestamp(),
        )

        result = svc.fetch_return_detail("TEST", "stock")
        yearly_candle = result["rows"][0]["candle"]
        assert yearly_candle == {
            "open": 54.0,
            "high": 65.0,
            "low": 53.0,
            "close": 63.0,
            "open_return": 8.0,
            "high_return": 30.0,
            "low_return": 6.0,
            "close_return": 26.0,
            "amplitude": 12.0,
            "amplitude_percent": 22.64,
        }
        assert yearly_candle["low_return"] <= min(
            yearly_candle["open_return"], yearly_candle["close_return"]
        )
        assert yearly_candle["high_return"] >= max(
            yearly_candle["open_return"], yearly_candle["close_return"]
        )

        january = result["rows"][0]["months"][0]["candle"]
        assert january["open"] == 54.0
        assert january["high"] == 62.0
        assert january["low"] == 53.0
        assert january["close"] == 60.0
        assert january["close_return"] == 20.0
        assert january["amplitude"] == 9.0
        assert january["amplitude_percent"] == 16.98

        selected = svc.fetch_return_detail("TEST", "stock", 2024)
        february = selected["monthly_returns"][1]["candle"]
        assert february["open_return"] == 0.0
        assert february["high_return"] == 8.33
        assert february["low_return"] == -8.33
        assert february["close_return"] == 5.0
        assert february["amplitude_percent"] == 18.18


class TestDetailAssetName:
    """The detail response carries a human-readable asset name."""

    def setup_method(self):
        svc.clear_price_change_cache()

    @staticmethod
    def _series(source="test"):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 4, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
        ]
        return PriceSeries(
            timestamps=[int(d.timestamp()) for d in dates],
            closes=[100.0, 110.0, 99.0, 108.9, 87.12, 120.0],
            raw_closes=[200.0, 210.0, 180.0, 190.0, 195.0, 220.0],
            source=source,
            fetched_at=dates[-1].timestamp(),
        )

    @patch("service.price_change.price_change_service.search_asset_symbols",
           return_value=[{"symbol": "BTC", "name": "Bitcoin", "type": "crypto"}])
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_crypto_detail_name_resolved_via_search(self, mock_fetch, mock_search):
        mock_fetch.return_value = self._series()
        result = svc.fetch_return_detail("BTC", "crypto")

        assert result["name"] == "Bitcoin"
        mock_search.assert_called_once_with("BTC", "crypto", 1)

    @patch("service.price_change.price_change_service.search_asset_symbols",
           return_value=[{"symbol": "159941", "name": "纳指ETF广发", "type": "cn_stock"}])
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_cn_stock_detail_name_resolved_via_search(self, mock_fetch, mock_search):
        mock_fetch.return_value = self._series()
        result = svc.fetch_return_detail("159941", "cn_stock")

        assert result["name"] == "纳指ETF广发"

    @patch("service.price_change.price_change_service.search_asset_symbols",
           return_value=[{"symbol": "AAPL", "name": "苹果", "type": "stock"}])
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_stock_detail_uses_search_when_fundamentals_lacks_name(self, mock_fetch, mock_search):
        mock_fetch.return_value = self._series()
        result = svc.fetch_return_detail("AAPL", "stock")

        assert result["name"] == "苹果"

    @patch("service.price_change.price_change_service._fetch_detail_fundamentals",
           return_value={"available": True, "name": "Apple Inc."})
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_stock_detail_prefers_fundamentals_name(self, mock_fetch, mock_fundamentals):
        mock_fetch.return_value = self._series(source="yahoo")
        result = svc.fetch_return_detail("AAPL", "stock")

        assert result["name"] == "Apple Inc."
        mock_fundamentals.assert_called_once_with("AAPL")


# ═══════════════════════════════════════════════════════════════════════════
# Stock comparison
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchStockComparison:
    """Compact annual comparison data for multiple US stocks."""

    def setup_method(self):
        svc.clear_price_change_cache()

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_builds_year_symbol_metric_cube_with_after_tax_dividends(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
        ]
        series = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[100.0, 105.0, 90.0, 110.0],
            raw_closes=[200.0, 210.0, 180.0, 220.0],
            source="yahoo",
            fetched_at=dates[-1].timestamp(),
            dividends=[
                {
                    "timestamp": int(datetime(2024, 3, 1, tzinfo=timezone.utc).timestamp()),
                    "amount": 0.25,
                },
                {
                    "timestamp": int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()),
                    "amount": 0.3,
                },
            ],
        )
        mock_fetch.return_value = series

        result = svc.fetch_stock_comparison(["aapl", "MSFT", "AAPL"], 30)

        assert result["symbols"] == ["AAPL", "MSFT"]
        assert result["currency"] == "USD"
        assert result["tax_rate"] == 30.0
        assert result["metrics"] == [
            "combined_annualized",
            "annual_return",
            "dividend_yield_after_tax",
            "max_drawdown",
        ]
        assert result["years"] == [2024, 2023]
        assert result["data"]["2024"]["AAPL"] == {
            "combined_annualized": 10.1926,
            "annual_return": 10.0,
            "dividend_yield_after_tax": 0.1925,
            "max_drawdown": -14.29,
        }
        assert result["data"]["2023"]["AAPL"]["combined_annualized"] is None
        assert result["meta"]["MSFT"]["source"] == "yahoo"

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_dividend_reinvestment_compounds_and_drives_backtest_curve(self, mock_fetch):
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
            datetime(2024, 3, 1, 12, tzinfo=timezone.utc),
            datetime(2024, 6, 3, 12, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
        ]
        mock_fetch.return_value = PriceSeries(
            timestamps=[int(item.timestamp()) for item in dates],
            closes=[100.0] * len(dates),
            raw_closes=[100.0] * len(dates),
            source="yahoo",
            fetched_at=dates[-1].timestamp(),
            dividends=[
                {"timestamp": int(datetime(2024, 3, 1, tzinfo=timezone.utc).timestamp()), "amount": 10.0},
                {"timestamp": int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()), "amount": 10.0},
            ],
        )

        reinvested = svc.fetch_stock_comparison(
            ["SPY"], 0, True, True, "2024-01-01",
        )
        svc.clear_price_change_cache()
        cash_only = svc.fetch_stock_comparison(
            ["SPY"], 0, False, True, "2024-01-01",
        )

        assert reinvested["data"]["2024"]["SPY"]["combined_annualized"] == 21.0
        assert cash_only["data"]["2024"]["SPY"]["combined_annualized"] == 20.0
        assert reinvested["backtest"]["curves"]["SPY"][-1]["total_return_pct"] == 21.0
        assert cash_only["backtest"]["curves"]["SPY"][-1]["total_return_pct"] == 20.0

    @pytest.mark.parametrize("start_date", [None, "", "not-a-date"])
    def test_backtest_requires_valid_start_date(self, start_date):
        with pytest.raises(ValueError, match="start_date"):
            svc.fetch_stock_comparison(["SPY"], backtest_enabled=True, start_date=start_date)

    def test_rejects_non_boolean_stock_compare_options(self):
        with pytest.raises(ValueError, match="include_dividend_reinvestment"):
            svc.fetch_stock_comparison(["SPY"], include_dividend_reinvestment="yes")
        with pytest.raises(ValueError, match="backtest_enabled"):
            svc.fetch_stock_comparison(["SPY"], backtest_enabled=1)

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_keeps_partial_failures_in_meta(self, mock_fetch):
        good = make_series(years=2)
        bad = PriceSeries(
            timestamps=[],
            closes=[],
            source="yahoo",
            fetched_at=time.time(),
            error="not found",
        )
        mock_fetch.side_effect = lambda symbol, _asset_type: bad if symbol == "BAD" else good

        result = svc.fetch_stock_comparison(["AAPL", "BAD"])

        assert result["data"]
        assert result["meta"]["AAPL"]["error"] is None
        assert result["meta"]["BAD"]["error"] == "not found"

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_reuses_cached_aggregate_response(self, mock_fetch):
        mock_fetch.return_value = make_series(years=2)

        first = svc.fetch_stock_comparison(["SPY", "QQQ"], 30)
        second = svc.fetch_stock_comparison(["SPY", "QQQ"], 30)

        assert second == first
        assert mock_fetch.call_count == 2

    def test_stock_comparison_cache_roundtrips_through_l2(self):
        payload = {
            "symbols": ["SPY", "QQQ"],
            "years": [2024],
            "meta": {
                "SPY": {"error": None},
                "QQQ": {"error": None},
            },
        }
        cache_key = svc._stock_compare_cache_key(["SPY", "QQQ"], 30.0)
        with patch.object(svc.cache_store, "cache_set") as mock_set:
            svc._set_cached_stock_comparison(cache_key, payload)
        raw = mock_set.call_args.args[1]
        svc._STOCK_COMPARE_CACHE.clear()

        with patch.object(svc.cache_store, "cache_get", return_value=raw):
            cached = svc._get_cached_stock_comparison(cache_key)

        assert cached == payload
        assert cache_key in svc._STOCK_COMPARE_CACHE

    def test_partial_failure_uses_short_stock_comparison_cache_ttl(self):
        payload = {
            "meta": {
                "SPY": {"error": None},
                "BAD": {"error": "not found"},
            },
        }
        cache_key = svc._stock_compare_cache_key(["SPY", "BAD"], 30.0)

        with patch.object(svc.cache_store, "cache_set"):
            svc._set_cached_stock_comparison(cache_key, payload)

        assert svc._STOCK_COMPARE_CACHE[cache_key][1] == svc.ERROR_CACHE_TTL_SECONDS

    def test_stock_comparison_cache_does_not_outlive_source_series(self):
        nearly_expired = datetime.fromtimestamp(
            time.time() - svc.DAILY_SERIES_TTL_SECONDS + 120,
            tz=timezone.utc,
        ).isoformat()
        payload = {
            "meta": {
                "SPY": {"error": None, "updated_at": nearly_expired},
                "QQQ": {"error": None, "updated_at": nearly_expired},
            },
        }
        cache_key = svc._stock_compare_cache_key(["SPY", "QQQ"], 30.0)

        with patch.object(svc.cache_store, "cache_set"):
            svc._set_cached_stock_comparison(cache_key, payload)

        assert 115 <= svc._STOCK_COMPARE_CACHE[cache_key][1] <= 120

    @pytest.mark.parametrize("tax_rate", [-1, 101, "abc", float("nan")])
    def test_rejects_invalid_tax_rate(self, tax_rate):
        with pytest.raises(ValueError, match="tax_rate"):
            svc.fetch_stock_comparison(["AAPL"], tax_rate)

    def test_rejects_more_than_eight_symbols(self):
        with pytest.raises(ValueError, match="at most 8"):
            svc.fetch_stock_comparison([f"S{i}" for i in range(9)])


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

    def test_serialize_roundtrip_preserves_raw_closes(self):
        series = PriceSeries(
            timestamps=[1],
            closes=[50.0],
            raw_closes=[100.0],
            source="test",
            fetched_at=time.time(),
        )
        result = svc._deserialize_series(svc._serialize_series(series))
        assert result is not None
        assert result.raw_closes == [100.0]

    def test_serialize_roundtrip_preserves_dividends(self):
        series = PriceSeries(
            timestamps=[1],
            closes=[50.0],
            source="test",
            fetched_at=time.time(),
            dividends=[{"timestamp": 1, "amount": 0.25}],
        )
        result = svc._deserialize_series(svc._serialize_series(series))
        assert result is not None
        assert result.dividends == [{"timestamp": 1, "amount": 0.25}]

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


class TestMarketPulse:
    """Fixed global benchmark strip."""

    @patch("service.price_change.price_change_service._market_pulse_yahoo_quotes", return_value=[])
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_returns_markets_in_display_order_with_summary(self, mock_fetch, mock_quotes):
        def series_for(symbol, asset_type):
            closes = {
                "000001": [100.0, 101.0],
                "^KS11": [100.0, 99.0],
                "^GSPC": [100.0, 102.0],
                "^NDX": [100.0, 100.0],
                "BTC": [100.0, 103.0],
            }[symbol]
            timestamps = [1704067200, 1704153600]
            return PriceSeries(timestamps, closes, "test", time.time())

        mock_fetch.side_effect = series_for
        result = svc.fetch_market_pulse()

        assert [item["symbol"] for item in result["markets"]] == [
            "000001", "^KS11", "^GSPC", "^NDX", "BTC",
        ]
        assert result["markets"][0]["price"] == 101.0
        assert result["markets"][0]["change_pct"] == 1.0
        assert result["markets"][0]["trade_date"] == "2024-01-02"
        assert "trend" not in result["markets"][0]
        assert result["summary"] == {"up": 3, "down": 1, "flat": 1, "available": 5}

    @patch("service.price_change.price_change_service._market_pulse_yahoo_quotes", return_value=[])
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_one_failure_does_not_hide_other_markets(self, mock_fetch, mock_quotes):
        def series_for(symbol, asset_type):
            if symbol == "^KS11":
                return empty_series("yahoo", "upstream failed")
            return PriceSeries([1704067200, 1704153600], [100.0, 101.0], "test", time.time())

        mock_fetch.side_effect = series_for
        result = svc.fetch_market_pulse()
        korea = next(item for item in result["markets"] if item["symbol"] == "^KS11")

        assert korea["price"] is None
        assert "trend" not in korea
        assert korea["error"] == "upstream failed"
        assert result["summary"]["available"] == 4

    @patch("service.price_change.price_change_service._market_pulse_yahoo_quotes")
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_batches_yahoo_indices_and_fetches_only_cn_and_btc_separately(self, mock_fetch, mock_quotes):
        mock_quotes.return_value = [
            {"symbol": "^KS11", "price": 2600.0, "change_pct": -1.2, "trade_time": 1704153600},
            {"symbol": "^GSPC", "price": 4800.0, "change_pct": 0.5, "trade_time": 1704153600},
            {"symbol": "^NDX", "price": 16800.0, "change_pct": 0.8, "trade_time": 1704153600},
        ]

        def series_for(symbol, asset_type):
            closes = {"000001": [100.0, 101.0], "BTC": [100.0, 103.0]}[symbol]
            return PriceSeries([1704067200, 1704153600], closes, "test", time.time())

        mock_fetch.side_effect = series_for
        result = svc.fetch_market_pulse()

        mock_quotes.assert_called_once_with(["^KS11", "^GSPC", "^NDX"])
        assert {call.args for call in mock_fetch.call_args_list} == {
            ("000001", "cn_stock"), ("BTC", "crypto"),
        }
        korea = next(item for item in result["markets"] if item["symbol"] == "^KS11")
        assert korea["price"] == 2600.0
        assert korea["change_pct"] == -1.2
        assert korea["trade_date"] == "2024-01-02"
        assert korea["source"] == "yahoo-quote"

    @patch("service.price_change.price_change_service._market_pulse_yahoo_quotes")
    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_partial_yahoo_batch_falls_back_only_for_missing_index(self, mock_fetch, mock_quotes):
        mock_quotes.return_value = [
            {"symbol": "^GSPC", "price": 4800.0, "change_pct": 0.5, "trade_time": 1704153600},
            {"symbol": "^NDX", "price": 16800.0, "change_pct": 0.8, "trade_time": 1704153600},
        ]

        def series_for(symbol, asset_type):
            closes = {
                "000001": [100.0, 101.0], "BTC": [100.0, 103.0], "^KS11": [100.0, 99.0],
            }[symbol]
            return PriceSeries([1704067200, 1704153600], closes, "test", time.time())

        mock_fetch.side_effect = series_for
        svc.fetch_market_pulse()

        assert {call.args for call in mock_fetch.call_args_list} == {
            ("000001", "cn_stock"), ("BTC", "crypto"), ("^KS11", "stock"),
        }


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
        assert "drawdowns" in result
        assert "meta" in result
        assert "AAPL" in result["data"]
        assert "AAPL" in result["drawdowns"]
        assert all(
            "max_drawdown" in row
            for row in result["drawdowns"]["AAPL"].values()
        )
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

    def test_hk_stock_symbol_is_canonicalized(self, mock_fetch_daily_series, three_year_series):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.fetch_yearly_returns([{"symbol": "00700", "type": "hk_stock"}])

        assert "0700.HK" in result["data"]
        assert result["meta"]["0700.HK"]["type"] == "hk_stock"
        mock_fetch_daily_series.assert_called_once_with("0700.HK", "hk_stock")

    def test_global_stock_keeps_yahoo_exchange_suffix(self, mock_fetch_daily_series, three_year_series):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.fetch_yearly_returns([{"symbol": "2330.tw", "type": "global_stock"}])

        assert "2330.TW" in result["data"]
        assert result["meta"]["2330.TW"]["type"] == "global_stock"
        mock_fetch_daily_series.assert_called_once_with("2330.TW", "global_stock")

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
        assert result["drawdowns"] == {}
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
        assert all("month" in r and "return" in r and "max_drawdown" in r for r in result)
        assert all("peak_date" in r and "trough_date" in r for r in result)
        diagnose("monthly results sample", [(r["month"], r["return"]) for r in result[:3]])
        track_coverage(MOD, 2)

    def test_unknown_asset_type(self, mock_fetch_daily_series):
        """Unknown asset type → 12 None entries."""
        mock_fetch_daily_series.return_value = empty_series(None, "unknown")
        result = svc.fetch_monthly_returns("XXX", "futures", 2024)
        assert len(result) == 12
        assert all(r["return"] is None for r in result)
        assert all(r["max_drawdown"] is None for r in result)
        track_coverage(MOD, 1)

    def test_error_series(self, mock_fetch_daily_series, error_series):
        """Series with fetch error → 12 None entries."""
        mock_fetch_daily_series.return_value = error_series
        result = svc.fetch_monthly_returns("AAPL", "stock", 2024)
        assert len(result) == 12
        assert all(r["return"] is None for r in result)
        assert all(r["max_drawdown"] is None for r in result)
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
        assert "AAPL" in result["data"]
        assert "GOOGL" in result["data"]
        assert len(result["data"]["AAPL"]) == 12
        assert "2024" in result["drawdowns"]["AAPL"]
        assert "max_drawdown" in result["drawdowns"]["AAPL"]["2024"]
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

    def test_hk_stock_uses_canonical_symbol_and_hkd(self, mock_fetch_daily_series, three_year_series):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.run_dca_backtest({
            "symbol": "700",
            "type": "hk_stock",
            "start_date": "2023-01-03",
            "end_date": "2024-06-28",
            "frequency": "monthly",
            "amount": 1000,
        })

        assert result["symbol"] == "0700.HK"
        assert result["type"] == "hk_stock"
        assert result["currency"] == "HKD"
        mock_fetch_daily_series.assert_called_once_with("0700.HK", "hk_stock")

    def test_global_stock_uses_exchange_currency(self, mock_fetch_daily_series, three_year_series):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.run_dca_backtest({
            "symbol": "7203.t",
            "type": "global_stock",
            "start_date": "2023-01-03",
            "end_date": "2024-06-28",
            "frequency": "monthly",
            "amount": 1000,
        })

        assert result["symbol"] == "7203.T"
        assert result["type"] == "global_stock"
        assert result["currency"] == "JPY"
        mock_fetch_daily_series.assert_called_once_with("7203.T", "global_stock")

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
        assert result["period_type"] == "day"
        assert result["period_days"] is None
        diagnose("crash summary", result["summary"])
        track_coverage(MOD, 2)

    def test_cn_stock_accepted(self, mock_fetch_daily_series):
        """cn_stock (A-share) is a supported crash-stats asset type."""
        from tests.conftest import make_crash_data
        ts, closes = make_crash_data()
        series = PriceSeries(ts, closes, "test-crash", time.time())
        mock_fetch_daily_series.return_value = series

        result = svc.run_crash_stats({
            "symbol": "159696",
            "type": "cn_stock",
            "start_date": "2022-01-01",
            "end_date": "2025-12-31",
            "threshold_pct": 3.0,
        })

        assert result["symbol"] == "159696"
        assert result["type"] == "cn_stock"
        assert result["summary"]["total_crashes"] >= 1

    def test_n_day_period_is_returned_and_applied(self, mock_fetch_daily_series):
        """Service builds non-overlapping N-day candles."""
        dates = [
            datetime(2023, 12, 29, 12, tzinfo=timezone.utc),
            *[
                datetime(2024, 1, day, 12, tzinfo=timezone.utc)
                for day in range(1, 7)
            ],
        ]
        mock_fetch_daily_series.return_value = PriceSeries(
            [int(day.timestamp()) for day in dates],
            [100.0, 97.0, 96.0, 90.0, 90.0, 93.0, 100.0],
            "test-crash",
            time.time(),
        )

        result = svc.run_crash_stats({
            "symbol": "test",
            "type": "stock",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "threshold_pct": 5.0,
            "period_type": "n_days",
            "period_days": 3,
        })

        assert result["period_type"] == "n_days"
        assert result["period_days"] == 3
        assert result["summary"]["total_crashes"] == 1
        assert result["crashes"][0]["period_start_date"] == "2024-01-01"
        track_coverage(MOD, 3)

    def test_daily_period_uses_previous_adjusted_close_not_current_open(
        self,
        mock_fetch_daily_series,
    ):
        """Daily crash detection includes an overnight gap down."""
        dates = [
            datetime(2024, 1, day, 12, tzinfo=timezone.utc)
            for day in range(1, 3)
        ]
        mock_fetch_daily_series.return_value = PriceSeries(
            [int(day.timestamp()) for day in dates],
            [50.0, 45.0],
            "test-crash",
            time.time(),
            opens=[50.0, 44.0],
        )

        result = svc.run_crash_stats({
            "symbol": "test",
            "type": "stock",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "threshold_pct": 5.0,
        })

        assert result["summary"]["total_crashes"] == 1
        assert result["crashes"][0]["pre_crash_close"] == 50.0
        assert result["crashes"][0]["crash_close"] == 45.0
        assert result["crashes"][0]["drop_pct"] == -10.0
        track_coverage(MOD, 4)

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

    def test_hk_stock_crash_stats_use_canonical_symbol(
        self,
        mock_fetch_daily_series,
        three_year_series,
    ):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.run_crash_stats({
            "symbol": "09988",
            "type": "hk_stock",
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "threshold_pct": 10.0,
        })

        assert result["symbol"] == "9988.HK"
        assert result["type"] == "hk_stock"
        mock_fetch_daily_series.assert_called_once_with("9988.HK", "hk_stock")

    def test_global_stock_crash_stats_keep_exchange_suffix(
        self,
        mock_fetch_daily_series,
        three_year_series,
    ):
        mock_fetch_daily_series.return_value = three_year_series

        result = svc.run_crash_stats({
            "symbol": "asml.as",
            "type": "global_stock",
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "threshold_pct": 10.0,
        })

        assert result["symbol"] == "ASML.AS"
        assert result["type"] == "global_stock"
        mock_fetch_daily_series.assert_called_once_with("ASML.AS", "global_stock")

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
        with pytest.raises(ValueError, match="period_type"):
            svc.run_crash_stats({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "period_type": "quarter",
            })
        with pytest.raises(ValueError, match="period_days"):
            svc.run_crash_stats({
                "symbol": "AAPL",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "period_type": "n_days",
                "period_days": 1,
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
# run_fear_threshold_stats
# ═══════════════════════════════════════════════════════════════════════════

class TestRunFearThresholdStats:
    """VIX/VXN threshold-day forward return analysis."""

    @staticmethod
    def _series(values, source):
        timestamps = [
            int((datetime(2024, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=i)).timestamp())
            for i in range(len(values))
        ]
        return PriceSeries(timestamps, values, source, time.time())

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_vix_threshold_returns_all_horizons_and_summary(self, mock_fetch):
        fear_values = [20.0] * 300
        fear_values[0] = 35.0
        fear_values[10] = 40.0
        fear_values[299] = 45.0
        fear_series = self._series(fear_values, "fear-source")
        asset_series = self._series([100.0 + i for i in range(300)], "asset-source")

        mock_fetch.side_effect = lambda symbol, _type: (
            fear_series if symbol == "^VIX" else asset_series
        )
        result = svc.run_fear_threshold_stats({
            "index": "VIX",
            "threshold": 30,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        })

        assert result["asset"] == "SPY"
        assert result["summary"]["event_count"] == 3
        assert result["events"][0]["date"] == "2024-10-26"
        assert result["events"][0]["forward"]["day_1"] is None
        oldest = result["events"][-1]
        assert oldest["asset_price"] == 100.0
        assert oldest["forward"]["day_1"] == {
            "date": "2024-01-02", "price": 101.0, "return_pct": 1.0,
        }
        assert oldest["forward"]["year_1"]["price"] == 352.0
        assert result["summary"]["horizons"]["year_1"]["available"] == 2
        assert result["meta"] == {
            "fear_source": "fear-source",
            "asset_source": "asset-source",
            "fear_points": 300,
            "asset_points": 300,
        }
        assert {call.args[0] for call in mock_fetch.call_args_list} == {"^VIX", "SPY"}
        track_coverage(MOD, 6)

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_vxn_uses_qqq_and_only_counts_dates_in_range(self, mock_fetch):
        fear_series = self._series([25.0, 45.0, 50.0, 20.0], "yahoo")
        asset_series = self._series([400.0, 404.0, 408.0, 412.0], "yahoo")
        mock_fetch.side_effect = lambda symbol, _type: (
            fear_series if symbol == "^VXN" else asset_series
        )

        result = svc.run_fear_threshold_stats({
            "index": "vxn",
            "threshold": 40,
            "start_date": "2024-01-02",
            "end_date": "2024-01-02",
        })

        assert result["index"] == "VXN"
        assert result["asset"] == "QQQ"
        assert result["summary"]["event_count"] == 1
        assert result["events"][0]["fear_value"] == 45.0
        assert result["events"][0]["forward"]["day_1"]["return_pct"] == 0.99
        assert {call.args[0] for call in mock_fetch.call_args_list} == {"^VXN", "QQQ"}
        track_coverage(MOD, 4)

    @pytest.mark.parametrize("payload,error", [
        ({"index": "VVIX", "threshold": 30, "start_date": "2024-01-01", "end_date": "2024-01-02"}, "index"),
        ({"index": "VIX", "threshold": 0, "start_date": "2024-01-01", "end_date": "2024-01-02"}, "threshold"),
        ({"index": "VIX", "threshold": "bad", "start_date": "2024-01-01", "end_date": "2024-01-02"}, "threshold"),
        ({"index": "VIX", "threshold": 30, "start_date": "2024-01-03", "end_date": "2024-01-02"}, "end_date"),
    ])
    def test_validation_errors(self, payload, error):
        with pytest.raises(ValueError, match=error):
            svc.run_fear_threshold_stats(payload)

    @patch("service.price_change.price_change_service._fetch_daily_series_cached")
    def test_data_source_error_is_runtime_error(self, mock_fetch):
        mock_fetch.return_value = PriceSeries([], [], "yahoo", time.time(), "upstream down")
        with pytest.raises(RuntimeError, match="failed to load"):
            svc.run_fear_threshold_stats({
                "index": "VIX",
                "threshold": 30,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            })


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
                        "regularMarketTime": 1704153600,
                        "regularMarketVolume": 1000000,
                        "marketCap": 3000000000000,
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "fullExchangeName": "NasdaqGS",
                        "trailingPE": 31.5,
                        "forwardPE": 28.2,
                        "priceToBook": 45.0,
                        "epsTrailingTwelveMonths": 6.4,
                        "dividendYield": 0.52,
                        "beta": 1.2,
                        "fiftyTwoWeekHigh": 200.0,
                        "fiftyTwoWeekLow": 120.0,
                        "averageDailyVolume3Month": 50000000,
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
        assert result[0]["trade_time"] == 1704153600
        assert result[0]["volume"] == 1000000
        assert result[0]["market_cap"] == 3000000000000
        assert result[0]["quote_type"] == "EQUITY"
        assert result[0]["currency"] == "USD"
        assert result[0]["exchange"] == "NasdaqGS"
        assert result[0]["trailing_pe"] == 31.5
        assert result[0]["forward_pe"] == 28.2
        assert result[0]["price_to_book"] == 45.0
        assert result[0]["eps_ttm"] == 6.4
        assert result[0]["dividend_yield"] == 0.52
        assert result[0]["beta"] == 1.2
        assert result[0]["fifty_two_week_high"] == 200.0
        assert result[0]["fifty_two_week_low"] == 120.0
        assert result[0]["average_volume_3m"] == 50000000
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


class TestDetailFundamentals:
    """Valuation snapshots are normalized and cached independently."""

    def setup_method(self):
        svc.clear_price_change_cache()

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_normalizes_quote_snapshot_and_uses_cache(self, mock_batch):
        mock_batch.return_value = [{
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "price": 150.0,
            "quote_type": "EQUITY",
            "currency": "USD",
            "exchange": "NasdaqGS",
            "market_cap": 3_000_000_000_000,
            "total_assets": None,
            "trailing_pe": 30.5,
            "forward_pe": 27.2,
            "price_to_book": 42.0,
            "eps_ttm": 6.3,
            "eps_forward": 7.1,
            "dividend_yield": 0.52,
            "trailing_dividend_yield": 0.0052,
            "beta": 1.2,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 100.0,
            "average_volume_3m": 50_000_000,
            "shares_outstanding": 15_000_000_000,
            "expense_ratio": None,
            "ytd_return": None,
            "three_year_return": None,
            "five_year_average_return": None,
        }]

        first = svc._fetch_detail_fundamentals("AAPL")
        second = svc._fetch_detail_fundamentals("AAPL")

        assert first["available"] is True
        assert first["name"] == "Apple Inc."
        assert first["market_cap"] == 3_000_000_000_000
        assert first["trailing_pe"] == 30.5
        assert first["dividend_yield"] == 0.52
        assert first["distance_to_52w_high"] == -25.0
        assert first["distance_to_52w_low"] == 50.0
        assert first["position_in_52w_range"] == 50.0
        assert first["field_count"] >= 10
        assert second == first
        mock_batch.assert_called_once_with(["AAPL"])

    @patch("service.price_change.price_change_service._eastmoney_detail_quote")
    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_empty_quote_uses_short_error_cache(self, mock_batch, mock_eastmoney):
        mock_batch.return_value = []
        mock_eastmoney.return_value = None

        first = svc._fetch_detail_fundamentals("MISSING")
        second = svc._fetch_detail_fundamentals("MISSING")

        assert first == {
            "available": False,
            "source": "yahoo_quote,eastmoney_quote",
            "field_count": 0,
        }
        assert second == first
        mock_batch.assert_called_once_with(["MISSING"])
        mock_eastmoney.assert_called_once_with("MISSING")

    @patch("service.price_change.price_change_service._eastmoney_detail_quote")
    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_uses_eastmoney_when_yahoo_quote_is_unavailable(
        self,
        mock_batch,
        mock_eastmoney,
    ):
        mock_batch.return_value = []
        mock_eastmoney.return_value = {
            "symbol": "AAPL",
            "name": "Apple",
            "price": 150.0,
            "quote_type": "EQUITY",
            "currency": "USD",
            "market_cap": 3_000_000_000_000,
            "trailing_pe": 30.0,
            "price_to_book": 40.0,
            "shares_outstanding": 15_000_000_000,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 100.0,
        }

        result = svc._fetch_detail_fundamentals("AAPL")

        assert result["available"] is True
        assert result["source"] == "eastmoney_quote"
        assert result["market_cap"] == 3_000_000_000_000
        assert result["trailing_pe"] == 30.0
        assert result["position_in_52w_range"] == 50.0

    @patch("service.price_change.price_change_service._em_session")
    def test_eastmoney_quote_scales_price_and_ratios(self, mock_session):
        response = MagicMock()
        response.json.return_value = {
            "data": {
                "f43": 339490,
                "f57": "AAPL",
                "f58": "Apple",
                "f59": 3,
                "f84": 14_687_356_000,
                "f116": 4_986_210_488_440,
                "f152": 2,
                "f163": 4452,
                "f167": 4682,
                "f172": "USD",
                "f174": 342890,
                "f175": 200625,
            }
        }
        mock_session.get.return_value = response

        result = svc._eastmoney_detail_quote("AAPL")

        assert result == {
            "symbol": "AAPL",
            "name": "Apple",
            "price": 339.49,
            "quote_type": "EQUITY",
            "currency": "USD",
            "market_cap": 4_986_210_488_440,
            "trailing_pe": 44.52,
            "price_to_book": 46.82,
            "shares_outstanding": 14_687_356_000,
            "fifty_two_week_high": 342.89,
            "fifty_two_week_low": 200.625,
        }
        response.raise_for_status.assert_called_once()


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
    def test_hk_stocks_use_batch_quote_and_hkd(self, mock_batch):
        mock_batch.return_value = [{
            "symbol": "0700.HK",
            "name": "Tencent Holdings Limited",
            "price": 475.2,
            "change_pct": 1.25,
            "volume": 12_000_000,
            "market_cap": 4.5e12,
            "currency": "HKD",
        }]

        result = svc._build_heatmap_today(
            [("0700.HK", "hk_stock")],
            set(),
            {"0700.HK"},
            auto_top_n=1,
            include_market_cap=True,
            compute_fn=self._compute_stub,
        )

        mock_batch.assert_called_once_with(["0700.HK"])
        item = result["data"][0]
        assert item["type"] == "hk_stock"
        assert item["turnover"] == 5_702_400_000.0
        assert item["turnover_currency"] == "HKD"
        assert item["market_cap"] == 4.5e12
        assert item["market_cap_currency"] == "HKD"

    @patch("service.price_change.price_change_service._yahoo_quote_batch")
    def test_global_stock_uses_suffix_currency_and_market(self, mock_batch):
        mock_batch.return_value = [{
            "symbol": "7203.T",
            "name": "Toyota Motor Corporation",
            "price": 2823.0,
            "change_pct": -0.04,
            "volume": 26_000_000,
            "market_cap": 33.4e12,
        }]

        result = svc._build_heatmap_today(
            [("7203.T", "stock")],
            set(),
            {"7203.T"},
            auto_top_n=1,
            include_market_cap=False,
            compute_fn=self._compute_stub,
        )

        item = result["data"][0]
        assert item["type"] == "stock"
        assert item["market"] == "JP"
        assert item["turnover_currency"] == "JPY"
        assert item["market_cap_currency"] == "JPY"

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

    @pytest.mark.parametrize(
        ("market_type", "candidate", "asset_type"),
        [
            ("stock", "AAPL", "stock"),
            ("hk_stock", "0700.HK", "hk_stock"),
            ("global_stock", "7203.T", "stock"),
            ("crypto", "BTC", "crypto"),
            ("cn_stock", "600519", "cn_stock"),
        ],
    )
    @patch("service.price_change.price_change_service._build_heatmap_today")
    def test_selected_market_uses_complete_pool(
        self, mock_build, market_type, candidate, asset_type
    ):
        mock_build.return_value = {
            "period": "today",
            "period_label": "1d",
            "data": [],
        }

        result = svc.fetch_heatmap_data(
            symbols=[],
            period="today",
            auto_top_n=0,
            market_type=market_type,
        )

        entries = mock_build.call_args.args[0]
        assert (candidate, asset_type) in entries
        assert mock_build.call_args.args[3] == len(entries)
        assert result["market_type"] == market_type

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
