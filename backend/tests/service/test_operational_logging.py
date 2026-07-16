"""Structured logging contracts for the unified financial data layer."""

import logging

from service.price_change import price_change_service as service
from tests.conftest import make_series


def test_daily_series_l1_cache_hit_is_logged(caplog):
    service.clear_price_change_cache()
    series = make_series(source="test-l1")
    service._set_cached_daily_series("LOG", "stock", series)
    caplog.set_level(logging.INFO, logger=service.__name__)

    result = service._fetch_daily_series_cached("LOG", "stock")

    assert result is series
    assert any(
        "event=daily_series_cache_hit" in record.getMessage()
        and "layer=l1" in record.getMessage()
        and "symbol=LOG" in record.getMessage()
        and "source=test-l1" in record.getMessage()
        for record in caplog.records
    )
    service.clear_price_change_cache()


def test_daily_series_fetch_success_is_logged(monkeypatch, caplog):
    service.clear_price_change_cache()
    monkeypatch.setitem(
        service._DAILY_SERIES_FETCHERS,
        "logging_test",
        lambda symbol: make_series(source=f"test-fetch-{symbol.lower()}"),
    )
    caplog.set_level(logging.INFO, logger=service.__name__)

    result = service._fetch_daily_series_cached("LOG", "logging_test")

    assert result.source == "test-fetch-log"
    messages = [record.getMessage() for record in caplog.records]
    assert any("event=daily_series_fetch_start symbol=LOG asset_type=logging_test" in message for message in messages)
    assert any(
        "event=daily_series_fetch_complete" in message
        and "symbol=LOG" in message
        and "source=test-fetch-log" in message
        and "success=True" in message
        and "duration_ms=" in message
        for message in messages
    )
    service.clear_price_change_cache()
