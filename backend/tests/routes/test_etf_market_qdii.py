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
    etf_market._qdii_holdings_cache.clear()
    yield
    etf_market._qdii_fund_cache.clear()
    etf_market._qdii_holdings_cache.clear()


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


def _sample_holdings(code="005698", stored_at=None):
    stored = time.time() if stored_at is None else stored_at
    return {
        "code": code,
        "status": "direct",
        "regions": [
            {"name": "中国内地", "bucket": "cn", "market_value": 7441065251.05, "nav_pct": 36.61},
            {"name": "中国香港", "bucket": "hk", "market_value": 4708485225.99, "nav_pct": 23.17},
            {"name": "美国", "bucket": "us", "market_value": 3385297797.45, "nav_pct": 16.66},
        ],
        "region_summary": {"cn": 36.61, "hk": 23.17, "us": 16.66, "other": 0.0},
        "direct_equity_pct": 76.44,
        "fund_positions": [{"name": "Direxion Daily Semiconductor Bull 3X ETF", "market_value": 1742633039.94, "nav_pct": 8.57}],
        "fund_investment_pct": 8.57,
        "report": {
            "id": "AN202607211827190245",
            "title": "华夏全球科技先锋混合型证券投资基金(QDII)2026年第2季度报告",
            "published_date": "2026-07-21",
            "url": "https://pdf.dfcfw.com/pdf/H2_AN202607211827190245_1.pdf",
        },
        "updated_at": "2026-08-03T00:00:00+00:00",
        "stored_at_epoch": stored,
        "cache_ttl_seconds": etf_market._QDII_HOLDINGS_TTL_SECONDS,
        "source": "test",
    }


class TestQdiiHoldingsParsing:
    def test_parses_region_buckets_and_aggregates_other_markets(self):
        text = """
5.2 报告期末在各个国家（地区）证券市场的股票及存托凭证投资分布
国家（地区） 公允价值（人民币元） 占基金资产净值比例（%）
中国内地 7,441,065,251.05 36.61
中国香港 4,708,485,225.99 23.17
美国 3,385,297,797.45 16.66
日本 100,000,000.00 1.25
合计 15,634,848,274.49 77.69
5.3 报告期末按行业分类
"""
        regions, summary = etf_market._parse_qdii_regions(text)

        assert [row["bucket"] for row in regions] == ["cn", "hk", "us", "other"]
        assert summary == {"cn": 36.61, "hk": 23.17, "us": 16.66, "other": 1.25}

    def test_parses_separately_disclosed_fund_and_etf_positions(self):
        text = """
5.9 报告期末按公允价值占基金资产净值比例大小排序的前十名基金投资明细
序号 基金名称 基金类型 运作方式 管理人 公允价值（元） 占基金资产净值比例（%）
1
Direxion Daily
Semiconductor Bull 3X ETF
权益类 交易型开放式 Rafferty Asset Management LLC
1,742,633,039.94 8.57
2
CSOP SK Hynix Daily 2x Leveraged Product
权益类 交易型开放式 CSOP Asset Management Ltd
205,794,063.29 1.01
5.10 投资组合报告附注
"""
        positions = etf_market._parse_qdii_fund_positions(text)

        assert [row["name"] for row in positions] == [
            "Direxion Daily Semiconductor Bull 3X ETF",
            "CSOP SK Hynix Daily 2x Leveraged Product",
        ]
        assert [row["nav_pct"] for row in positions] == [8.57, 1.01]
        assert etf_market._has_qdii_fund_exposure(text) is True

    def test_no_direct_equity_or_fund_positions_returns_empty_lists(self):
        text = """
5.2 报告期末在各个国家（地区）证券市场的股票及存托凭证投资分布
本基金本报告期末未持有股票及存托凭证。
5.9 报告期末按公允价值占基金资产净值比例大小排序的前十名基金投资明细
本基金本报告期末未持有基金。
5.10 投资组合报告附注
"""
        regions, summary = etf_market._parse_qdii_regions(text)

        assert regions == []
        assert summary == {"cn": 0.0, "hk": 0.0, "us": 0.0, "other": 0.0}
        assert etf_market._parse_qdii_fund_positions(text) == []
        assert etf_market._has_qdii_fund_exposure(text) is False

    def test_detects_fund_exposure_when_pdf_table_cells_are_fragmented(self):
        text = """
5.2 期末投资目标基金明细
序号 基金名称 基金类型 运作方式 管理人 公允价值（人民币元） 占基金资
产净值比
例（%）
1
纳指 ETF 汇添富 股票型 交易型开放式 汇添富基金管理股份有限公司
2,828,901
,241.40
91.10
5.3 报告期末在各个国家（地区）证券市场的股票及存托凭证投资分布
"""

        assert etf_market._parse_qdii_fund_positions(text) == []
        assert etf_market._has_qdii_fund_exposure(text) is True


class TestQdiiHoldingsRoute:
    def test_rejects_invalid_fund_code(self, client):
        response = client.get(f"{BASE}/abc/holdings")

        assert response.status_code == 400
        assert "6 digits" in response.get_json()["error"]

    def test_fetches_and_then_reuses_memory_cache(self, client):
        payload = _sample_holdings()
        with patch("routes.etf_market._read_qdii_holdings_shared_cache", return_value=None), \
             patch("routes.etf_market._write_qdii_holdings_shared_cache"), \
             patch("routes.etf_market._fetch_qdii_holdings", return_value=payload) as fetch:
            first = client.get(f"{BASE}/005698/holdings")
            second = client.get(f"{BASE}/005698/holdings")

        assert first.status_code == 200
        assert first.get_json()["cache_status"] == "fresh"
        assert second.get_json()["cache_status"] == "memory"
        assert second.get_json()["region_summary"]["cn"] == 36.61
        fetch.assert_called_once_with("005698")

    def test_uses_shared_cache_without_refetching(self, client):
        payload = _sample_holdings()
        with patch("routes.etf_market._read_qdii_holdings_shared_cache", return_value=payload), \
             patch("routes.etf_market._fetch_qdii_holdings") as fetch:
            response = client.get(f"{BASE}/005698/holdings")

        assert response.status_code == 200
        assert response.get_json()["cache_status"] == "shared"
        fetch.assert_not_called()

    def test_returns_unreported_as_valid_business_status(self, client):
        payload = _sample_holdings(code="028491")
        payload.update({"status": "unreported", "regions": [], "report": None})
        with patch("routes.etf_market._read_qdii_holdings_shared_cache", return_value=None), \
             patch("routes.etf_market._write_qdii_holdings_shared_cache"), \
             patch("routes.etf_market._fetch_qdii_holdings", return_value=payload):
            response = client.get(f"{BASE}/028491/holdings")

        assert response.status_code == 200
        assert response.get_json()["status"] == "unreported"

    def test_serves_stale_report_when_upstream_refresh_fails(self, client):
        stale = _sample_holdings(stored_at=time.time() - etf_market._QDII_HOLDINGS_TTL_SECONDS - 10)
        with patch("routes.etf_market._read_qdii_holdings_shared_cache", return_value=stale), \
             patch("routes.etf_market._fetch_qdii_holdings", side_effect=RuntimeError("timeout")):
            response = client.get(f"{BASE}/005698/holdings")

        assert response.status_code == 200
        assert response.get_json()["cache_status"] == "stale_upstream_failed"
        assert "served cached" in response.get_json()["warning"]
