"""Tests for QDII fund tracker route and data mapping."""

import time
from unittest.mock import Mock, patch

import pytest

import routes.etf_market as etf_market

BASE = "/api/etf-market/qdii-funds"


def _sample_payload(code="017641", stored_at=None):
    stored = time.time() if stored_at is None else stored_at
    return {
        "groups": {
            "nasdaq100": [],
            "sp500": [{
                "index": "sp500",
                "code": code,
                "name": "摩根标普500指数(QDII)人民币A",
                "company": "摩根基金",
                "fund_type": "指数型-海外股票",
                "share_class": "A",
                "purchase_status": "开放申购",
                "redeem_status": "开放赎回",
                "buyable": True,
                "min_purchase": 10.0,
                "daily_limit": None,
                "source_rate": "1.20%",
                "discounted_rate": "0.12%",
                "source_rate_num": 1.2,
                "discounted_rate_num": 0.12,
                "fund_scale": 2465625910.24,
                "fund_manager": "张军",
                "daily_return_pct": 1.56,
                "return_1m_pct": 1.35,
                "return_3m_pct": 12.16,
                "return_6m_pct": 7.23,
                "return_1y_pct": 19.11,
                "return_3y_pct": 54.7,
                "return_since_inception_pct": 68.44,
                "nav": "1.6844",
                "nav_date": "2026-06-15",
                "source_url": f"https://fund.eastmoney.com/{code}.html",
            }],
            "active_qdii": [],
        },
        "summary": {"sp500": {"total": 1, "buyable": 1}},
        "labels": {"nasdaq100": "纳指100", "sp500": "标普500", "active_qdii": "QDII主动"},
        "discovered_counts": {"nasdaq100": 0, "sp500": 1, "active_qdii": 0},
        "errors": [],
        "updated_at": "2026-06-17T00:00:00+00:00",
        "stored_at_epoch": stored,
        "cache_ttl_seconds": etf_market._QDII_FUND_TTL_SECONDS,
        "cache_status": "fresh",
        "source": "test",
        "disclaimer": "test",
    }


@pytest.fixture(autouse=True)
def reset_qdii_memory_cache():
    etf_market._qdii_fund_cache.clear()
    yield
    etf_market._qdii_fund_cache.clear()


class TestQdiiFundsRoute:
    def test_shared_cache_is_used_across_requests(self, client):
        payload = _sample_payload(code="shared")
        with patch("routes.etf_market._read_qdii_shared_cache", return_value=payload), \
             patch("routes.etf_market._read_qdii_snapshot", return_value=None), \
             patch("routes.etf_market._fetch_all_qdii_fund_groups") as fetch_all:
            resp = client.get(f"{BASE}?index=sp500")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache_status"] == "shared"
        assert data["cache_ttl_seconds"] == 4 * 60 * 60
        assert data["groups"]["sp500"][0]["code"] == "shared"
        fetch_all.assert_not_called()

    def test_normal_request_uses_memory_cache_before_refetching(self, client):
        payload = _sample_payload(code="memory")
        with patch("routes.etf_market._read_qdii_shared_cache", return_value=None), \
             patch("routes.etf_market._read_qdii_snapshot", return_value=None), \
             patch("routes.etf_market._write_qdii_shared_cache"), \
             patch("routes.etf_market._write_qdii_snapshot"), \
             patch("routes.etf_market._fetch_all_qdii_fund_groups", return_value=payload) as fetch_all:
            first = client.get(f"{BASE}?index=sp500")
            second = client.get(f"{BASE}?index=sp500")

        assert first.status_code == 200
        assert first.get_json()["cache_status"] == "fresh"
        assert second.status_code == 200
        assert second.get_json()["cache_status"] == "memory"
        assert fetch_all.call_count == 1

    def test_fresh_request_bypasses_shared_cache_and_refetches(self, client):
        shared_payload = _sample_payload(code="shared")
        fresh_payload = _sample_payload(code="fresh")
        with patch("routes.etf_market._read_qdii_shared_cache", return_value=shared_payload), \
             patch("routes.etf_market._read_qdii_snapshot", return_value=None), \
             patch("routes.etf_market._write_qdii_shared_cache"), \
             patch("routes.etf_market._write_qdii_snapshot"), \
             patch("routes.etf_market._fetch_all_qdii_fund_groups", return_value=fresh_payload) as fetch_all:
            resp = client.get(f"{BASE}?index=sp500&fresh=1")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache_status"] == "fresh"
        assert data["groups"]["sp500"][0]["code"] == "fresh"
        assert resp.headers["Cache-Control"] == "no-store"
        fetch_all.assert_called_once()

    def test_normal_response_does_not_create_separate_cdn_long_cache(self, client):
        payload = _sample_payload()
        with patch("routes.etf_market._read_qdii_shared_cache", return_value=payload), \
             patch("routes.etf_market._fetch_all_qdii_fund_groups") as fetch_all:
            resp = client.get(f"{BASE}?index=sp500")

        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
        assert resp.headers["CDN-Cache-Control"] == "no-store"
        assert resp.headers["Vercel-CDN-Cache-Control"] == "no-store"
        fetch_all.assert_not_called()


class TestQdiiFundInfoMapping:
    def test_fetch_qdii_fund_info_maps_new_fields(self):
        class Resp:
            def __init__(self, body):
                self._body = body

            def raise_for_status(self):
                return None

            def json(self):
                return self._body

        base_body = {
            "Datas": {
                "SGZT": "开放申购",
                "SHZT": "开放赎回",
                "SOURCERATE": "1.20%",
                "RATE": "0.12%",
                "SHORTNAME": "摩根标普500指数(QDII)人民币A",
                "BUY": True,
                "MINSG": "10",
                "JJGS": "摩根基金",
                "FTYPE": "指数型-海外股票",
                "FEGM": "2465625910.24",
                "JJJL": "张军",
                "RZDF": "1.56",
                "SYL_Y": "1.30",
                "SYL_3Y": "12.00",
                "SYL_6Y": "7.00",
                "SYL_1N": "19.00",
                "DWJZ": "1.6844",
                "FSRQ": "2026-06-15",
            }
        }
        period_body = {
            "Datas": [
                {"title": "Y", "syl": "1.35"},
                {"title": "3Y", "syl": "12.16"},
                {"title": "6Y", "syl": "7.23"},
                {"title": "1N", "syl": "19.11"},
                {"title": "3N", "syl": "54.70"},
                {"title": "LN", "syl": "68.44"},
            ]
        }

        mock_get = Mock(side_effect=[Resp(base_body), Resp(period_body)])
        with patch("routes.etf_market.requests.get", mock_get):
            row = etf_market._fetch_qdii_fund_info("017641", "sp500")

        assert row["fund_scale"] == 2465625910.24
        assert row["fund_manager"] == "张军"
        assert row["daily_return_pct"] == 1.56
        assert row["return_1m_pct"] == 1.35
        assert row["return_3m_pct"] == 12.16
        assert row["return_6m_pct"] == 7.23
        assert row["return_1y_pct"] == 19.11
        assert row["return_3y_pct"] == 54.7
        assert row["return_since_inception_pct"] == 68.44
