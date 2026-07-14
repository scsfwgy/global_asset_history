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
