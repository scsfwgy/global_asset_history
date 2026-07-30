"""Tests for US-stock valuation and profitability history."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from service.price_change import fundamentals_history as history


def test_parse_yahoo_valuation_payload_normalizes_series_and_latest():
    """A wrong field dispatch or sign filter must not corrupt PE/PB history."""
    payload = {
        "timeseries": {
            "result": [
                {
                    "meta": {"type": ["quarterlyPeRatio"]},
                    "quarterlyPeRatio": [
                        {
                            "asOfDate": "2024-03-31",
                            "reportedValue": {"raw": 28.5},
                        },
                        {
                            "asOfDate": "2024-06-30",
                            "reportedValue": {"raw": 30.25},
                        },
                        {
                            "asOfDate": "2024-09-30",
                            "reportedValue": {"raw": -4.0},
                        },
                    ],
                },
                {
                    "quarterlyPbRatio": [
                        {
                            "asOfDate": "2024-03-31",
                            "reportedValue": {"raw": 40.0},
                        },
                        {
                            "asOfDate": "2024-06-30",
                            "reportedValue": {"raw": 0},
                        },
                    ],
                },
                {
                    "trailingPeRatio": [
                        {
                            "asOfDate": "2024-07-01",
                            "reportedValue": {"raw": 31.2},
                        }
                    ],
                },
                {
                    "trailingPbRatio": [
                        {
                            "asOfDate": "2024-07-01",
                            "reportedValue": {"raw": 42.4},
                        }
                    ],
                },
            ]
        }
    }

    assert history._parse_yahoo_valuation_payload(payload) == {
        "pe": [
            {"date": "2024-03-31", "value": 28.5},
            {"date": "2024-06-30", "value": 30.25},
        ],
        "pb": [{"date": "2024-03-31", "value": 40.0}],
        "latest_pe": 31.2,
        "latest_pb": 42.4,
    }


def test_parse_yahoo_valuation_payload_rejects_malformed_points():
    """Malformed dates and non-finite values must not leak into chart JSON."""
    payload = {
        "timeseries": {
            "result": [
                {
                    "quarterlyPeRatio": [
                        {
                            "asOfDate": "not-a-date",
                            "reportedValue": {"raw": 20},
                        },
                        {
                            "asOfDate": "2024-03-31",
                            "reportedValue": {"raw": "nan"},
                        },
                        None,
                    ],
                }
            ]
        }
    }

    assert history._parse_yahoo_valuation_payload(payload) == {
        "pe": [],
        "pb": [],
        "latest_pe": None,
        "latest_pb": None,
    }


def test_parse_eastmoney_roe_payload_accepts_annual_negative_values():
    """Dropping negative ROE would hide the companies where the metric matters most."""
    payload = {
        "result": {
            "data": [
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "2024-12-31 00:00:00",
                    "ROE_AVG": -4.5,
                },
                {
                    "DATE_TYPE_CODE": "003",
                    "REPORT_DATE": "2024-03-31 00:00:00",
                    "ROE_AVG": 2.0,
                },
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "2023-12-31 00:00:00",
                    "ROE": 11.25,
                },
            ]
        }
    }

    assert history._parse_eastmoney_roe_payload(payload) == [
        {"date": "2023-12-31", "value": 11.25},
        {"date": "2024-12-31", "value": -4.5},
    ]


def test_parse_eastmoney_roe_payload_deduplicates_report_dates():
    """Duplicate revised rows must produce one deterministic chart point."""
    payload = {
        "result": {
            "data": [
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "2024-12-31 00:00:00",
                    "ROE_AVG": 12.5,
                },
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "2024-12-31 00:00:00",
                    "ROE_AVG": 13.0,
                },
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "invalid",
                    "ROE_AVG": 99.0,
                },
            ]
        }
    }

    assert history._parse_eastmoney_roe_payload(payload) == [
        {"date": "2024-12-31", "value": 12.5},
    ]


def test_fetch_yahoo_valuation_history_requests_all_required_types():
    """The source adapter must request both historical and latest PE/PB fields."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "timeseries": {
            "result": [
                {
                    "quarterlyPeRatio": [
                        {
                            "asOfDate": "2024-03-31",
                            "reportedValue": {"raw": 25.0},
                        }
                    ]
                },
                {
                    "trailingPeRatio": [
                        {
                            "asOfDate": "2024-04-01",
                            "reportedValue": {"raw": 26.0},
                        }
                    ]
                },
            ]
        }
    }
    session = MagicMock()
    session.get.return_value = response

    with patch.object(history, "_yahoo_session", session), patch.object(
        history,
        "_get_yahoo_crumb",
        return_value="crumb-token",
    ):
        result = history._fetch_yahoo_valuation_history("AAPL")

    assert result["pe"] == [{"date": "2024-03-31", "value": 25.0}]
    assert result["latest_pe"] == 26.0
    params = session.get.call_args.kwargs["params"]
    assert params["type"] == (
        "quarterlyPeRatio,quarterlyPbRatio,"
        "trailingPeRatio,trailingPbRatio"
    )
    assert params["period1"] < params["period2"]
    assert params["crumb"] == "crumb-token"
    response.raise_for_status.assert_called_once_with()


def test_fetch_yahoo_valuation_history_refreshes_crumb_once_after_403():
    """An expired Yahoo crumb should be refreshed before degrading the source."""
    forbidden = MagicMock(status_code=403)
    success = MagicMock(status_code=200)
    success.json.return_value = {"timeseries": {"result": []}}
    session = MagicMock()
    session.get.side_effect = [forbidden, success]

    with patch.object(history, "_yahoo_session", session), patch.object(
        history,
        "_get_yahoo_crumb",
        side_effect=["stale-crumb", "fresh-crumb"],
    ) as mock_crumb:
        result = history._fetch_yahoo_valuation_history("AAPL")

    assert result["pe"] == []
    assert session.get.call_count == 2
    assert session.get.call_args_list[0].kwargs["params"]["crumb"] == "stale-crumb"
    assert session.get.call_args_list[1].kwargs["params"]["crumb"] == "fresh-crumb"
    assert mock_crumb.call_args_list[1].kwargs == {"force_refresh": True}
    forbidden.raise_for_status.assert_not_called()
    success.raise_for_status.assert_called_once_with()


def test_get_yahoo_crumb_bootstraps_cookie_and_reuses_cached_value():
    """Yahoo's fundamentals endpoint requires a session cookie and crumb pair."""
    cookie_response = MagicMock()
    cookie_response.status_code = 200
    crumb_response = MagicMock()
    crumb_response.status_code = 200
    crumb_response.text = "valid-crumb"
    session = MagicMock()
    session.get.side_effect = [cookie_response, crumb_response]

    with patch.object(history, "_yahoo_session", session):
        history._clear_yahoo_crumb()
        assert history._get_yahoo_crumb() == "valid-crumb"
        assert history._get_yahoo_crumb() == "valid-crumb"

    assert session.get.call_count == 2
    cookie_response.raise_for_status.assert_not_called()
    crumb_response.raise_for_status.assert_called_once_with()


def test_fetch_yahoo_valuation_history_degrades_on_upstream_error():
    """Yahoo throttling must not turn a partial page into a server error."""
    session = MagicMock()
    session.get.side_effect = RuntimeError("rate limited")

    with patch.object(history, "_yahoo_session", session), patch.object(
        history,
        "_get_yahoo_crumb",
        return_value="crumb-token",
    ):
        assert history._fetch_yahoo_valuation_history("AAPL") == {
            "pe": [],
            "pb": [],
            "latest_pe": None,
            "latest_pb": None,
        }


def test_yahoo_crumb_failure_is_briefly_negative_cached():
    """A blocked crumb endpoint must not serialize every new symbol on I/O."""
    session = MagicMock()
    session.get.side_effect = RuntimeError("blocked")

    with patch.object(history, "_yahoo_session", session), patch.object(
        history.time,
        "time",
        return_value=1_000.0,
    ):
        history._clear_yahoo_crumb()
        assert history._get_yahoo_crumb() is None
        assert history._get_yahoo_crumb() is None

    assert session.get.call_count == 1


def test_fetch_eastmoney_roe_history_resolves_security_then_fetches_annual_rows():
    """The adapter must resolve Eastmoney's exchange-qualified US security code."""
    profile_response = MagicMock()
    profile_response.json.return_value = {
        "result": {"data": [{"SECUCODE": "AAPL.O", "SECURITY_CODE": "AAPL"}]}
    }
    indicator_response = MagicMock()
    indicator_response.json.return_value = {
        "result": {
            "data": [
                {
                    "DATE_TYPE_CODE": "001",
                    "REPORT_DATE": "2024-12-31 00:00:00",
                    "ROE_AVG": 17.5,
                }
            ]
        }
    }
    session = MagicMock()
    session.get.side_effect = [profile_response, indicator_response]

    with patch.object(history, "_eastmoney_session", session):
        result = history._fetch_eastmoney_roe_history("AAPL")

    assert result == [{"date": "2024-12-31", "value": 17.5}]
    assert session.get.call_count == 2
    first_params = session.get.call_args_list[0].kwargs["params"]
    second_params = session.get.call_args_list[1].kwargs["params"]
    assert first_params["reportName"] == "RPT_USF10_INFO_ORGPROFILE"
    assert '(SECURITY_CODE="AAPL")' in first_params["filter"]
    assert second_params["reportName"] == "RPT_USF10_FN_GMAININDICATOR"
    assert '(SECUCODE="AAPL.O")' in second_params["filter"]
    assert '(DATE_TYPE_CODE="001")' in second_params["filter"]
    profile_response.raise_for_status.assert_called_once_with()
    indicator_response.raise_for_status.assert_called_once_with()


def test_metric_stats_uses_current_value_and_requires_four_observations():
    """Changing the percentile boundary or sample gate must be detected."""
    points = [
        {"date": "2020-12-31", "value": 10.0},
        {"date": "2021-12-31", "value": 20.0},
        {"date": "2022-12-31", "value": 30.0},
        {"date": "2023-12-31", "value": 40.0},
    ]

    assert history._metric_stats(points, current=30.0, years=5) == {
        "median_5y": 25.0,
        "percentile_5y": 75.0,
    }
    assert history._metric_stats(points[:3], current=20.0, years=5) == {
        "median_5y": None,
        "percentile_5y": None,
    }
    assert history._metric_stats(points, current=None, years=5) == {
        "median_5y": 25.0,
        "percentile_5y": None,
    }


@patch.object(history, "_fetch_eastmoney_roe_history")
@patch.object(history, "_fetch_yahoo_valuation_history")
def test_fetch_history_merges_sources_and_calculates_latest(
    mock_yahoo,
    mock_eastmoney,
):
    """Losing one source field must not silently drop another metric."""
    history.clear_fundamentals_history_cache()
    mock_yahoo.return_value = {
        "pe": [
            {"date": "2021-03-31", "value": 20.0},
            {"date": "2022-03-31", "value": 25.0},
            {"date": "2023-03-31", "value": 30.0},
            {"date": "2024-03-31", "value": 35.0},
        ],
        "pb": [
            {"date": "2021-03-31", "value": 10.0},
            {"date": "2022-03-31", "value": 11.0},
            {"date": "2023-03-31", "value": 12.0},
            {"date": "2024-03-31", "value": 13.0},
        ],
        "latest_pe": 32.0,
        "latest_pb": 12.5,
    }
    mock_eastmoney.return_value = [
        {"date": "2021-12-31", "value": 15.0},
        {"date": "2022-12-31", "value": 16.0},
        {"date": "2023-12-31", "value": 17.0},
        {"date": "2024-12-31", "value": 18.0},
    ]

    with patch.object(history.cache_store, "cache_get", return_value=None), patch.object(
        history.cache_store,
        "cache_set",
        return_value=True,
    ) as mock_cache_set:
        result = history.fetch_fundamentals_history("aapl")

    assert result["symbol"] == "AAPL"
    assert result["available"] is True
    assert result["partial"] is False
    assert result["latest"] == {
        "pe": 32.0,
        "pb": 12.5,
        "roe": 18.0,
        "roe_report_date": "2024-12-31",
    }
    assert result["stats"]["pe"] == {
        "median_5y": 27.5,
        "percentile_5y": 75.0,
    }
    assert result["sources"] == {
        "pe": "yahoo_fundamentals_timeseries",
        "pb": "yahoo_fundamentals_timeseries",
        "roe": "eastmoney_us_financials",
    }
    assert mock_cache_set.call_args.args[2] == 24 * 60 * 60


@patch.object(history, "_fetch_eastmoney_roe_history")
@patch.object(history, "_fetch_yahoo_valuation_history")
def test_fetch_history_preserves_partial_roe_and_uses_short_empty_cache(
    mock_yahoo,
    mock_eastmoney,
):
    """A Yahoo failure must preserve ROE, while a total failure uses short TTL."""
    history.clear_fundamentals_history_cache()
    mock_yahoo.return_value = {
        "pe": [],
        "pb": [],
        "latest_pe": None,
        "latest_pb": None,
    }
    mock_eastmoney.return_value = [
        {"date": "2024-12-31", "value": -5.0},
    ]

    with patch.object(history.cache_store, "cache_get", return_value=None), patch.object(
        history.cache_store,
        "cache_set",
        return_value=True,
    ) as mock_cache_set:
        partial = history.fetch_fundamentals_history("LOSS")

    assert partial["available"] is True
    assert partial["partial"] is True
    assert partial["series"]["pe"] == []
    assert partial["latest"]["roe"] == -5.0
    assert mock_cache_set.call_args.args[2] == 24 * 60 * 60

    history.clear_fundamentals_history_cache()
    mock_eastmoney.return_value = []
    with patch.object(history.cache_store, "cache_get", return_value=None), patch.object(
        history.cache_store,
        "cache_set",
        return_value=True,
    ) as mock_cache_set:
        empty = history.fetch_fundamentals_history("EMPTY")

    assert empty["available"] is False
    assert empty["partial"] is False
    assert mock_cache_set.call_args.args[2] == 10 * 60


@patch.object(history, "_fetch_eastmoney_roe_history")
@patch.object(history, "_fetch_yahoo_valuation_history")
def test_fetch_history_uses_l1_then_deserialized_l2(
    mock_yahoo,
    mock_eastmoney,
):
    """Removing either cache layer must cause this contract test to fail."""
    history.clear_fundamentals_history_cache()
    mock_yahoo.return_value = {
        "pe": [{"date": "2024-03-31", "value": 20.0}],
        "pb": [],
        "latest_pe": 21.0,
        "latest_pb": None,
    }
    mock_eastmoney.return_value = []

    with patch.object(history.cache_store, "cache_get", return_value=None), patch.object(
        history.cache_store,
        "cache_set",
        return_value=True,
    ):
        first = history.fetch_fundamentals_history("AAPL")
        second = history.fetch_fundamentals_history("AAPL")

    assert second == first
    assert mock_yahoo.call_count == 1
    assert mock_eastmoney.call_count == 1

    history.clear_fundamentals_history_cache()
    with patch.object(
        history.cache_store,
        "cache_get",
        return_value=json.dumps(first),
    ), patch.object(history.cache_store, "cache_set", return_value=True):
        from_l2 = history.fetch_fundamentals_history("AAPL")

    assert from_l2 == first
    assert mock_yahoo.call_count == 1
    assert mock_eastmoney.call_count == 1


def test_l2_cache_only_warms_l1_for_its_remaining_lifetime():
    """A nearly expired shared entry must not become fresh for another 24 hours."""
    history.clear_fundamentals_history_cache()
    payload = {"symbol": "AAPL", "available": True}
    envelope = {
        "cached_at": 1_000.0,
        "ttl": 100,
        "payload": payload,
    }
    cache_key = history._cache_key("AAPL")

    with patch.object(
        history.cache_store,
        "cache_get",
        return_value=json.dumps(envelope),
    ), patch.object(history.time, "time", return_value=1_090.0), patch.object(
        history.time,
        "monotonic",
        return_value=5_000.0,
    ):
        assert history._cached_payload(cache_key) == payload

    assert history._HISTORY_CACHE[cache_key][0] == 5_010.0


@patch.object(history, "_fetch_eastmoney_roe_history")
@patch.object(history, "_fetch_yahoo_valuation_history")
def test_concurrent_requests_for_same_symbol_share_one_source_fetch(
    mock_yahoo,
    mock_eastmoney,
):
    """A cold-cache burst should not stampede both upstream data sources."""
    history.clear_fundamentals_history_cache()

    def slow_yahoo(_symbol):
        time.sleep(0.04)
        return {
            "pe": [],
            "pb": [],
            "latest_pe": None,
            "latest_pb": None,
        }

    def slow_eastmoney(_symbol):
        time.sleep(0.04)
        return []

    mock_yahoo.side_effect = slow_yahoo
    mock_eastmoney.side_effect = slow_eastmoney

    with patch.object(history.cache_store, "cache_get", return_value=None), patch.object(
        history.cache_store,
        "cache_set",
        return_value=True,
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(history.fetch_fundamentals_history, ["AAPL"] * 2))

    assert results[0] == results[1]
    assert mock_yahoo.call_count == 1
    assert mock_eastmoney.call_count == 1
    assert history._FETCH_LOCKS == {}


def test_l1_cache_is_bounded_and_sweeps_oldest_entries():
    """Valid-looking one-off symbols must not grow process memory forever."""
    history.clear_fundamentals_history_cache()
    with patch.object(history.cache_store, "cache_set", return_value=True):
        for index in range(history._MAX_MEMORY_CACHE_ENTRIES + 3):
            history._store_payload(
                history._cache_key(f"S{index}"),
                {"symbol": f"S{index}", "available": True},
                history._SUCCESS_TTL_SECONDS,
            )

    assert len(history._HISTORY_CACHE) == history._MAX_MEMORY_CACHE_ENTRIES
    assert history._cache_key("S0") not in history._HISTORY_CACHE
