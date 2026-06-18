"""Tests for ETF market history cache behaviour."""

import time
from unittest.mock import patch

import pytest

import routes.etf_market as etf_market

BASE = "/api/etf-market/history"


def _sample_history_payload(stored_at=None):
    stored = time.time() if stored_at is None else stored_at
    return {
        "symbol": "513300",
        "bars": [{
            "date": "2026-06-17",
            "open": 1.0,
            "close": 1.02,
            "high": 1.03,
            "low": 0.99,
            "volume": 1000.0,
            "amount": 100000.0,
            "change_pct": 2.0,
            "amplitude_pct": 4.0,
            "nav": 1.0,
            "nav_date": "2026-06-16",
            "premium_pct": 2.0,
        }],
        "count": 1,
        "has_premium": True,
        "premium_approx": False,
        "stats": {},
        "stored_at_epoch": stored,
        "cache_ttl_seconds": etf_market._ETF_HISTORY_TTL_SECONDS,
        "cache_status": "fresh",
    }


@pytest.fixture(autouse=True)
def reset_history_cache():
    etf_market._etf_history_cache.clear()
    yield
    etf_market._etf_history_cache.clear()


class TestEtfHistoryCache:
    def test_history_uses_fresh_memory_cache_without_network(self, client):
        key = etf_market._history_cache_key("513300", 120)
        etf_market._etf_history_cache[key] = (time.time(), _sample_history_payload())

        with patch("routes.etf_market.requests.get") as mock_get:
            resp = client.get(f"{BASE}?symbol=513300&days=120")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache_status"] == "memory"
        assert data["cache_ttl_seconds"] == 4 * 60 * 60
        assert data["bars"][0]["premium_pct"] == 2.0
        mock_get.assert_not_called()

    def test_history_serves_stale_cache_when_upstream_fails(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(etf_market, "_ETF_HISTORY_DATA_DIR", tmp_path)
        stored_at = time.time() - etf_market._ETF_HISTORY_TTL_SECONDS - 60
        key = etf_market._history_cache_key("513300", 120)
        etf_market._etf_history_cache[key] = (stored_at, _sample_history_payload(stored_at))

        with patch.object(etf_market.cache_store, "cache_get", return_value=None), patch(
            "routes.etf_market.requests.get",
            side_effect=etf_market.requests.RequestException("boom"),
        ):
            resp = client.get(f"{BASE}?symbol=513300&days=120")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache_status"] == "memory_stale_upstream_failed"
        assert "upstream fetch failed" in data["cache_error"]
        assert data["bars"][0]["premium_pct"] == 2.0

    def test_history_writes_and_reads_local_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(etf_market, "_ETF_HISTORY_DATA_DIR", tmp_path)

        payload = _sample_history_payload()
        with patch.object(etf_market.cache_store, "cache_set", return_value=True):
            etf_market._write_etf_history_cache("513300", 120, payload)

        assert etf_market._history_snapshot_path("513300", 120).exists()
        etf_market._etf_history_cache.clear()

        with patch.object(etf_market.cache_store, "cache_get", return_value=None):
            cached = etf_market._read_etf_history_cache("513300", 120)

        assert cached is not None
        assert cached["cache_status"] == "local"
        assert cached["bars"][0]["premium_pct"] == 2.0

    def test_nav_cached_reads_local_snapshot_without_upstream(self, tmp_path, monkeypatch):
        monkeypatch.setattr(etf_market, "_ETF_NAV_DATA_DIR", tmp_path)
        etf_market._nav_cache.clear()
        nav_map = {"2026-06-16": 1.0, "2026-06-17": 1.02}

        etf_market._write_etf_nav_snapshot("513300", "2026-06-16", "2026-06-17", nav_map)

        with patch.object(etf_market.cache_store, "cache_get", return_value=None), \
             patch.object(etf_market.cache_store, "cache_set", return_value=True), \
             patch("routes.etf_market._fetch_etf_nav") as fetch_nav:
            cached = etf_market._fetch_etf_nav_cached("513300", "2026-06-16", "2026-06-17")

        assert cached == nav_map
        fetch_nav.assert_not_called()
