"""Regression tests for the ETF historical returns matrix."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import routes.etf_market as etf_market


def _series(points):
    return SimpleNamespace(
        timestamps=[
            int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            for date, _ in points
        ],
        closes=[value for _, value in points],
        error=None,
    )


def test_strict_period_returns_require_adjacent_periods():
    values = [("2023-12-29", 100), ("2024-12-31", 120), ("2026-01-02", 150)]

    result = etf_market._strict_period_returns(values, "year", [2026, 2025, 2024])

    assert result == {"2026": None, "2025": None, "2024": 20.0}


def test_strict_month_returns_use_previous_december_for_january():
    values = [("2024-12-31", 100), ("2025-01-31", 110), ("2025-02-28", 99)]

    result = etf_market._strict_period_returns(
        values,
        "month",
        [(2025, 1), (2025, 2), (2025, 3)],
    )

    assert result == {"1": 10.0, "2": -10.0, "3": None}


def test_strict_period_returns_ignore_invalid_values_and_do_not_bridge_gaps():
    values = [
        ("2022-12-30", 100),
        ("2023-12-29", None),
        ("2024-12-31", float("inf")),
        ("2025-12-31", 120),
        ("2026-08-18", 132),
    ]

    result = etf_market._strict_period_returns(values, "year", [2026, 2025, 2024])

    assert result == {"2026": 10.0, "2025": None, "2024": None}


def test_strict_period_returns_calculate_current_month_mtd():
    values = [("2026-07-31", 100), ("2026-08-18", 107.5)]

    result = etf_market._strict_period_returns(values, "month", [(2026, 8), (2026, 9)])

    assert result == {"8": 7.5, "9": None}


def test_returns_matrix_separates_price_and_nav_and_keeps_benchmark(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: ("QQQ", [{"symbol": "513300", "name": "纳指ETF"}]),
    )
    calls = []

    def fake_series(symbol, asset_type):
        calls.append((symbol, asset_type))
        return _series([
            ("2024-12-31", 100),
            ("2025-12-31", 120),
            ("2026-06-30", 150),
        ])

    def fake_nav(symbol, start, end):
        assert symbol == "513300"
        assert start == "2024-01-01"
        assert end >= "2026-06-30"
        return {
            "2024-12-31": 100,
            "2025-12-31": 110,
            "2026-06-30": 121,
        }

    monkeypatch.setattr(etf_market, "_fetch_daily_series_cached", fake_series)
    monkeypatch.setattr(etf_market, "_fetch_etf_nav_cached", fake_nav)
    with patch.object(etf_market, "_RETURNS_MATRIX_YEAR_COUNT", 2):
        response = client.get(
            "/api/etf-market/returns-matrix?group=nasdaq100&mode=year"
        )

    assert response.status_code == 200
    data = response.get_json()
    assert [row["symbol"] for row in data["rows"]] == ["QQQ", "513300"]
    assert data["rows"][0]["with_premium"]["2026"] == 25.0
    assert data["rows"][0]["without_premium"]["2026"] == 25.0
    assert data["rows"][1]["with_premium"]["2026"] == 25.0
    assert data["rows"][1]["without_premium"]["2026"] == 10.0
    assert ("QQQ", "stock") in calls
    assert ("513300", "cn_stock") in calls


def test_returns_matrix_month_mode_returns_mtd_and_null_for_future_months(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: ("SPY", [{"symbol": "513650", "name": "标普ETF"}]),
    )
    values = [
        ("2025-12-31", 100),
        ("2026-01-30", 105),
        ("2026-02-27", 110),
        ("2026-08-18", 121),
    ]
    monkeypatch.setattr(
        etf_market,
        "_fetch_daily_series_cached",
        lambda *args: _series(values),
    )
    monkeypatch.setattr(
        etf_market,
        "_fetch_etf_nav_cached",
        lambda *args: dict(values),
    )

    response = client.get(
        "/api/etf-market/returns-matrix?group=sp500&mode=month&year=2026"
    )

    assert response.status_code == 200
    row = response.get_json()["rows"][0]
    assert row["with_premium"]["1"] == 5.0
    assert row["with_premium"]["2"] == 4.76
    assert row["with_premium"]["8"] is None
    assert row["with_premium"]["9"] is None


def test_returns_matrix_is_partial_success_when_one_symbol_fails(client, monkeypatch):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: ("SPY", [{"symbol": "513650", "name": "标普ETF"}]),
    )

    def fake_series(symbol, asset_type):
        if symbol == "513650":
            raise RuntimeError("price unavailable")
        return _series([("2025-12-31", 100), ("2026-06-30", 110)])

    monkeypatch.setattr(etf_market, "_fetch_daily_series_cached", fake_series)
    monkeypatch.setattr(etf_market, "_fetch_etf_nav_cached", lambda *args: {})
    with patch.object(etf_market, "_RETURNS_MATRIX_YEAR_COUNT", 1):
        response = client.get(
            "/api/etf-market/returns-matrix?group=sp500&mode=year"
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["rows"][1]["with_premium"]["2026"] is None
    assert any(
        error["symbol"] == "513650" and error["stage"] == "price"
        for error in data["errors"]
    )


def test_returns_matrix_records_nav_failure_without_dropping_row(client, monkeypatch):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: ("SPY", [{"symbol": "513650", "name": "标普ETF"}]),
    )
    monkeypatch.setattr(
        etf_market,
        "_fetch_daily_series_cached",
        lambda *args: _series([("2025-12-31", 100), ("2026-06-30", 110)]),
    )

    def fail_nav(*args):
        raise RuntimeError("nav unavailable")

    monkeypatch.setattr(etf_market, "_fetch_etf_nav_cached", fail_nav)
    with patch.object(etf_market, "_RETURNS_MATRIX_YEAR_COUNT", 1):
        response = client.get(
            "/api/etf-market/returns-matrix?group=sp500&mode=year"
        )

    assert response.status_code == 200
    data = response.get_json()
    assert [row["symbol"] for row in data["rows"]] == ["SPY", "513650"]
    assert data["rows"][1]["with_premium"]["2026"] == 10.0
    assert data["rows"][1]["without_premium"]["2026"] is None
    assert any(
        error["symbol"] == "513650" and error["stage"] == "nav"
        for error in data["errors"]
    )


def test_returns_matrix_returns_500_for_invalid_configuration(client, monkeypatch):
    def fail_config(group):
        raise RuntimeError("ETF configuration is empty")

    monkeypatch.setattr(etf_market, "_load_returns_matrix_group", fail_config)

    response = client.get(
        "/api/etf-market/returns-matrix?group=sp500&mode=year"
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "ETF configuration is empty"


def test_returns_matrix_preserves_configured_order_when_workers_finish_out_of_order(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: (
            "QQQ",
            [
                {"symbol": "513300", "name": "第一只"},
                {"symbol": "513110", "name": "第二只"},
            ],
        ),
    )

    class ReversedExecutor:
        def __init__(self, **kwargs):
            self._futures = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def submit(self, fn, item):
            class Future:
                pass

            future = Future()
            future.result = lambda: fn(item)
            self._futures.append(future)
            return future

    monkeypatch.setattr(etf_market, "ThreadPoolExecutor", ReversedExecutor)
    monkeypatch.setattr(
        etf_market,
        "as_completed",
        lambda futures: reversed(list(futures)),
    )
    monkeypatch.setattr(
        etf_market,
        "_fetch_daily_series_cached",
        lambda *args: _series([("2025-12-31", 100), ("2026-06-30", 110)]),
    )
    monkeypatch.setattr(
        etf_market,
        "_fetch_etf_nav_cached",
        lambda *args: {"2025-12-31": 100, "2026-06-30": 110},
    )
    with patch.object(etf_market, "_RETURNS_MATRIX_YEAR_COUNT", 1):
        response = client.get(
            "/api/etf-market/returns-matrix?group=nasdaq100&mode=year"
        )

    assert response.status_code == 200
    assert [row["symbol"] for row in response.get_json()["rows"]] == [
        "QQQ",
        "513300",
        "513110",
    ]


def test_returns_matrix_returns_502_when_all_values_are_missing(client, monkeypatch):
    monkeypatch.setattr(
        etf_market,
        "_load_returns_matrix_group",
        lambda group: ("SPY", [{"symbol": "513650", "name": "标普ETF"}]),
    )
    monkeypatch.setattr(
        etf_market,
        "_fetch_daily_series_cached",
        lambda *args: _series([]),
    )
    monkeypatch.setattr(etf_market, "_fetch_etf_nav_cached", lambda *args: {})

    response = client.get("/api/etf-market/returns-matrix?group=sp500&mode=year")

    assert response.status_code == 502
    assert response.get_json()["error"] == "no return data available"


def test_returns_matrix_validates_parameters(client):
    assert client.get(
        "/api/etf-market/returns-matrix?group=global_others"
    ).status_code == 400
    assert client.get(
        "/api/etf-market/returns-matrix?group=sp500&mode=bad"
    ).status_code == 400
    assert client.get(
        "/api/etf-market/returns-matrix?group=sp500&mode=month"
    ).status_code == 400
    assert client.get(
        "/api/etf-market/returns-matrix?group=sp500&mode=month&year=2020"
    ).status_code == 400
