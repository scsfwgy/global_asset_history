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
    etf_market._ETF_EST_DATE_CACHE.clear()
    yield
    etf_market._etf_history_cache.clear()
    etf_market._ETF_EST_DATE_CACHE.clear()


class TestEtfEstDate:
    """The ETF fund establishment date comes from the East Money profile."""

    @staticmethod
    def _jbgk_resp(html):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.content = html.encode("utf-8")
        return resp

    @staticmethod
    def _page(est):
        return f"<html><th>成立日期/规模</th><td>{est} / 2.697亿份</td></html>"

    def test_parses_establishment_date(self):
        with patch(
            "routes.etf_market._em_trust_env_session.get",
            return_value=self._jbgk_resp(self._page("2022年07月21日")),
        ) as mock_get:
            result = etf_market._fetch_etf_est_date("159632")

        assert result == "2022-07-21"
        assert "jbgk_159632.html" in mock_get.call_args[0][0]

    def test_returns_none_when_profile_missing_date(self):
        with patch(
            "routes.etf_market._em_trust_env_session.get",
            return_value=self._jbgk_resp("<html>no date</html>"),
        ):
            assert etf_market._fetch_etf_est_date("999999") is None

    def test_memoized_within_ttl(self):
        etf_market._ETF_EST_DATE_CACHE["513300"] = ("2013-05-15", time.time())

        with patch("routes.etf_market._em_trust_env_session.get") as mock_get:
            result = etf_market._fetch_etf_est_date("513300")

        assert result == "2013-05-15"
        mock_get.assert_not_called()


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
        """When upstream fails, fallback to local snapshot (not expired in-memory cache).

        The test validates that the system has proper fallback layers:
        1. Fresh in-memory cache (L1)
        2. Shared Redis cache (L2)
        3. Local file snapshot (L3) ← fallback when upstream fails

        Expired in-memory cache should be cleaned up, not kept as fallback.
        """
        monkeypatch.setattr(etf_market, "_ETF_HISTORY_DATA_DIR", tmp_path)
        stored_at = time.time() - etf_market._ETF_HISTORY_TTL_SECONDS - 60

        # Write a stale snapshot to disk (this is the fallback layer)
        payload = _sample_history_payload(stored_at)
        etf_market._write_etf_history_snapshot("513300", 120, payload)

        # Clear in-memory cache to simulate it being cleaned up
        etf_market._etf_history_cache.clear()

        with patch.object(etf_market.cache_store, "cache_get", return_value=None), patch(
            "routes.etf_market.requests.get",
            side_effect=etf_market.requests.RequestException("boom"),
        ):
            resp = client.get(f"{BASE}?symbol=513300&days=120")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache_status"] == "local_stale_upstream_failed"
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

    def test_fetch_nav_traverses_short_pages_until_start_date(self):
        """East Money ignores pageSize, so short pages are not terminal."""
        from unittest.mock import MagicMock

        responses = []
        for page in range(1, 23):
            response = MagicMock()
            response.raise_for_status.return_value = None
            year = 2026 if page < 22 else 2024
            response.json.return_value = {
                "Data": {
                    "LSJZList": [{
                        "FSRQ": f"{year}-01-{min(page, 28):02d}",
                        "DWJZ": str(1 + page / 100),
                    }]
                }
            }
            responses.append(response)

        with patch(
            "routes.etf_market.requests.get",
            side_effect=responses,
        ) as mock_get:
            nav_map = etf_market._fetch_etf_nav(
                "513300",
                "2024-12-31",
                "2026-08-19",
            )

        assert mock_get.call_count == 22
        assert "2024-01-22" in nav_map

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
