"""Provider and cache regressions for the homepage quote path."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from service.price_change import fetchers, homepage_quotes, price_change_service as svc


@pytest.fixture(autouse=True)
def clear_quote_cache(monkeypatch):
    monkeypatch.setattr(homepage_quotes, "_cache", {source: {} for source in homepage_quotes._locks})


@pytest.mark.parametrize(("symbol", "pair"), [("BTC", "BTCUSDT"), ("TON", "GRAMUSDT")])
def test_binance_uses_previous_completed_close_and_reuses_it_for_the_same_day(monkeypatch, symbol, pair):
    today = datetime(2026, 11, 10, tzinfo=timezone.utc)
    midnight_ms = int(today.timestamp() * 1000)
    clock = Mock(wraps=datetime)
    clock.now.return_value = today
    monkeypatch.setattr(fetchers, "datetime", clock)
    current = Mock()
    current.json.return_value = [{
        "symbol": pair, "lastPrice": "101", "openPrice": "99", "priceChangePercent": "2",
        "quoteVolume": "1200000", "count": 20, "openTime": midnight_ms,
    }]
    candle = Mock()
    candle.json.return_value = [[0, "98", "102", "96", "100", "12", midnight_ms - 1]]
    get = Mock(side_effect=[current, candle, current])
    monkeypatch.setattr(fetchers._session, "get", get)

    result = fetchers.fetch_binance_home_quotes([symbol], {})
    quote = result[0]
    assert quote["price"] == 101
    assert quote["change_pct"] == pytest.approx(1)
    assert quote["turnover"] == 1200000
    assert "trade_time" not in quote
    assert quote["symbol"] == symbol
    assert get.call_args.kwargs["params"]["endTime"] == midnight_ms - 1
    assert get.call_args.kwargs["params"]["symbol"] == pair

    assert fetchers.fetch_binance_home_quotes([symbol], {symbol: quote}) == result
    assert get.call_count == 3


def test_tencent_uses_previous_close_exchange_timestamp_and_actual_turnover(monkeypatch):
    fields = [""] * 39
    fields[1], fields[2], fields[3], fields[4] = "贵州茅台", "600519", "1439.00", "1444.99"
    fields[30], fields[37] = "20261110161453", "331608"
    response = Mock(content=('v_sh600519="' + "~".join(fields) + '";\nv_sz000858="";').encode("gb18030"))
    monkeypatch.setattr(fetchers._session, "get", Mock(return_value=response))
    quote, = fetchers.fetch_tencent_home_quotes(["600519", "000858"], {})
    assert quote["trade_date"] == "2026-11-10"
    assert homepage_quotes.iso_time(quote["trade_time"]) == "2026-11-10T08:14:53+00:00"
    assert quote["price"] == 1439
    assert quote["change_pct"] == pytest.approx(-0.414536, abs=1e-6)
    assert quote["turnover"] == 3316080000


def test_cache_uses_shared_snapshot_throttles_force_and_labels_failed_refresh(monkeypatch):
    now = [1794304800]
    monkeypatch.setattr(homepage_quotes.time, "time", lambda: now[0])
    stored = {}
    monkeypatch.setattr(homepage_quotes.cache_store, "cache_get", stored.get)
    monkeypatch.setattr(homepage_quotes.cache_store, "cache_set", lambda key, value, ttl: stored.update({key: value}))
    fetch = Mock(side_effect=[[{"symbol": "BTC", "price": 100}], [], [{"symbol": "BTC", "price": 103}]])
    def load(force=False):
        return homepage_quotes.cached_quotes("binance-quote", ["BTC"], fetch, force)["BTC"]

    first = load()
    homepage_quotes._cache["binance-quote"].clear()
    now[0] += 5
    assert load(force=True) == first
    assert fetch.call_count == 1

    now[0] += 6
    stale = load(force=True)
    assert stale["price"] == 100
    assert stale["fetched_ts"] == first["fetched_ts"]
    assert stale["stale"] is True
    assert load() == stale
    assert fetch.call_count == 2

    now[0] += 61
    latest = load()
    assert latest["price"] == 103 and not latest["stale"]


def test_market_pulse_and_today_tiles_use_one_snapshot(monkeypatch):
    binance = Mock(return_value=[{"symbol": "BTC", "price": 74413.33, "change_pct": -1.23, "turnover": 100}])
    tencent = Mock(return_value=[{"symbol": "000001", "price": 3663.72, "change_pct": 0.08}])
    monkeypatch.setattr(svc, "fetch_binance_home_quotes", binance)
    monkeypatch.setattr(svc, "fetch_tencent_home_quotes", tencent)
    monkeypatch.setattr(svc, "_yahoo_quote_batch", lambda symbols: [])
    monkeypatch.setattr(svc, "_get_cached_daily_series", lambda *args: None)

    crypto = svc.fetch_heatmap_data([], "today", market_type="crypto", force_refresh=True)
    pulse = svc.fetch_market_pulse(force_refresh=True)
    china = svc.fetch_heatmap_data([{"symbol": "000001", "type": "cn_stock"}], "today", market_type="cn_stock")
    for symbol, tiles in (("BTC", crypto), ("000001", china)):
        tile = next(row for row in tiles["data"] if row["symbol"] == symbol)
        card = next(row for row in pulse["markets"] if row["symbol"] == symbol)
        for key in ("price", "source", "fetched_at", "stale"):
            assert tile[key] == card[key]
        assert tile["return_pct"] == card["change_pct"]
    assert binance.call_count == tencent.call_count == 1


def test_missing_quote_uses_daily_snapshot_with_original_date(monkeypatch):
    series = svc.PriceSeries([1794096000, 1794182400], [1453, 1444.99], "tencent", 1794291527)
    monkeypatch.setattr(svc, "_get_cached_daily_series", lambda *args: series)
    monkeypatch.setattr(svc, "fetch_tencent_home_quotes", lambda *args: [])
    result = svc.fetch_heatmap_data([{"symbol": "600519", "type": "cn_stock"}], "today")
    row, = result["data"]
    assert row["stale"] is True
    assert row["trade_date"] == "2026-11-09"
    assert row["fetched_at"] == homepage_quotes.iso_time(series.fetched_at)
    assert row["quote_at"] is None
