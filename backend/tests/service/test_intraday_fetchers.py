"""Unit tests for intraday market-data download fetchers."""

from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

from service.price_change import fetchers


def _response(body):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = body
    return response


@patch.object(fetchers._session, "get")
def test_yahoo_daily_preserves_raw_close_with_adjusted_close(mock_get):
    timestamp = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp())
    mock_get.return_value = _response({
        "chart": {"result": [{
            "timestamp": [timestamp],
            "indicators": {
                "quote": [{
                    "open": [98.0],
                    "high": [102.0],
                    "low": [97.0],
                    "close": [100.0],
                    "volume": [1000],
                }],
                "adjclose": [{"adjclose": [50.0]}],
            },
            "events": {
                "dividends": {
                    str(timestamp): {"date": timestamp, "amount": 0.25},
                },
            },
        }]},
    })

    series = fetchers._fetch_daily_series_stock_direct("TEST")

    assert series.closes == [50.0]
    assert series.raw_closes == [100.0]
    assert series.opens == [98.0]
    assert series.dividends == [{"timestamp": timestamp, "amount": 0.25}]
    assert mock_get.call_args.kwargs["params"]["events"] == "div,splits"


def test_yahoo_dividend_parser_skips_malformed_events():
    parsed = fetchers._parse_yahoo_dividends({
        "events": {
            "dividends": {
                "3": {"date": 3, "amount": 0.3},
                "bad": {"amount": "nope"},
                "2": {"date": 2, "amount": 0},
                "1": {"date": 1, "amount": 0.1},
            },
        },
    })

    assert parsed == [
        {"timestamp": 1, "amount": 0.1},
        {"timestamp": 3, "amount": 0.3},
    ]


@patch.object(fetchers._session, "get")
def test_binance_intraday_parses_ohlcv(mock_get):
    timestamp_ms = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
    mock_get.return_value = _response([[
        timestamp_ms, "100", "105", "98", "103", "42", timestamp_ms + 59999,
    ]])
    series = fetchers.fetch_intraday_series("BTC", "crypto", "1m", date(2024, 1, 2), date(2024, 1, 2))
    assert series.error is None
    assert series.source == "binance"
    assert series.closes == [103.0]
    assert series.opens == [100.0]
    assert series.volumes == [42.0]
    assert mock_get.call_args.kwargs["params"]["interval"] == "1m"


@patch.object(fetchers._session, "get")
def test_yahoo_four_hour_aggregates_hourly_bars(mock_get):
    base = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp())
    timestamps = [base + hour * 3600 for hour in range(4)]
    mock_get.return_value = _response({
        "chart": {"result": [{
            "timestamp": timestamps,
            "indicators": {"quote": [{
                "open": [10.0, 11.0, 12.0, 13.0],
                "high": [12.0, 13.0, 14.0, 15.0],
                "low": [9.0, 10.0, 11.0, 12.0],
                "close": [11.0, 12.0, 13.0, 14.0],
                "volume": [1.0, 2.0, 3.0, 4.0],
            }]},
        }]},
    })
    series = fetchers.fetch_intraday_series("AAPL", "stock", "4h", date(2024, 1, 2), date(2024, 1, 2))
    assert series.timestamps == [base]
    assert series.opens == [10.0]
    assert series.highs == [15.0]
    assert series.lows == [9.0]
    assert series.closes == [14.0]
    assert series.volumes == [10.0]
    assert mock_get.call_args.kwargs["params"]["interval"] == "1h"


def test_a_share_intraday_returns_clear_error():
    series = fetchers.fetch_intraday_series("000001", "cn_stock", "1h", date(2024, 1, 2), date(2024, 1, 3))
    assert series.error == "intraday download is not supported for A-shares"


def test_a_share_exchange_mapping_distinguishes_indices_and_shenzhen_stocks():
    assert fetchers._cn_tencent_symbol("000001") == "sh000001"
    assert fetchers._cn_tencent_symbol("000333") == "sz000333"
    assert fetchers._cn_tencent_symbol("600519") == "sh600519"


@patch.object(fetchers._session, "get")
def test_eastmoney_a_share_uses_stock_exchange_mapping_and_handles_empty_data(
    mock_get,
):
    mock_get.return_value = _response({"data": None})

    series = fetchers._fetch_daily_series_cn_stock_eastmoney("000333")

    assert series.error == "empty data"
    assert mock_get.call_args.kwargs["params"]["secid"] == "0.000333"
