"""Tests for admin-only wishes VPN monitor and probe endpoints."""

from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from service.wishes import vpn_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WISH_ADMIN_TOKEN", "test-secret-token")
    app_module.app.config["TESTING"] = True
    with vpn_service._last_hit_lock:
        vpn_service._last_hit = None
    with app_module.app.test_client() as test_client:
        yield test_client


def test_vpn_endpoints_require_admin_token(client):
    r1 = client.get("/api/wishes/vpn-status")
    assert r1.status_code == 403

    r2 = client.post("/api/wishes/vpn-probe", headers={"X-Admin-Token": "wrong"})
    assert r2.status_code == 403


def test_vpn_status_unconfigured(client, monkeypatch):
    monkeypatch.delenv("MIHOMO_CONTROLLER_URL", raising=False)
    resp = client.get("/api/wishes/vpn-status", headers={"X-Admin-Token": "test-secret-token"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["configured"] is False


def test_vpn_status_returns_sorted_nodes_and_traffic(client, monkeypatch):
    monkeypatch.setenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("MIHOMO_PROXY_GROUP", "YahooAuto")

    proxies_payload = {
        "proxies": {
            "YahooAuto": {
                "type": "LoadBalance",
                "all": ["NodeB", "NodeA", "NodeOffline"],
            },
            "NodeA": {
                "type": "Shadowsocks",
                "alive": True,
                "history": [{"time": "2026-11-26T10:00:00Z", "delay": 120}],
            },
            "NodeB": {
                "type": "Trojan",
                "alive": True,
                "history": [{"time": "2026-11-26T10:00:00Z", "delay": 280}],
            },
            "NodeOffline": {
                "type": "VMess",
                "alive": False,
                "history": [{"time": "2026-11-26T10:00:00Z", "delay": 0}],
            },
        }
    }
    conns_payload = {
        "uploadTotal": 1024,
        "downloadTotal": 20480,
        "connections": [
            {"metadata": {"host": "query1.finance.yahoo.com"}, "chains": ["NodeA", "YahooAuto"]}
        ],
    }

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = proxies_payload if url.endswith("/proxies") else conns_payload
        return resp

    with patch.object(vpn_service._ctrl_session, "get", side_effect=fake_get):
        resp = client.get("/api/wishes/vpn-status", headers={"X-Admin-Token": "test-secret-token"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["configured"] is True
    assert data["group"]["total_nodes"] == 3
    assert data["group"]["alive_nodes"] == 2
    assert data["traffic"]["total_bytes"] == 21504
    assert [n["name"] for n in data["nodes"]] == ["NodeA", "NodeB", "NodeOffline"]
    assert data["nodes"][0]["delay_ms"] == 120
    assert data["nodes"][2]["delay_ms"] is None


def test_vpn_probe_captures_hit_node_and_latency(client, monkeypatch):
    monkeypatch.setenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")

    proxies_payload = {
        "proxies": {
            "YahooAuto": {"type": "LoadBalance", "all": ["NodeJP"]},
            "NodeJP": {"type": "Trojan", "alive": True, "history": [{"time": "2026-11-26T10:00:00Z", "delay": 195}]},
        }
    }
    conns_payload = {
        "uploadTotal": 500,
        "downloadTotal": 4000,
        "connections": [
            {"metadata": {"host": "query1.finance.yahoo.com"}, "chains": ["NodeJP", "YahooAuto"]}
        ],
    }

    def fake_ctrl_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = proxies_payload if url.endswith("/proxies") else conns_payload
        return resp

    fake_yahoo_resp = MagicMock()
    fake_yahoo_resp.status_code = 200
    fake_yahoo_resp.raw.read.return_value = b'{"chart":{}}'

    with patch.object(vpn_service._ctrl_session, "get", side_effect=fake_ctrl_get), \
         patch("service.wishes.vpn_service.requests.get", return_value=fake_yahoo_resp):
        resp = client.post(
            "/api/wishes/vpn-probe",
            json={"refresh_delays": False},
            headers={"X-Admin-Token": "test-secret-token"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["last_hit"]["node"] == "NodeJP"
    assert data["last_hit"]["node_delay_ms"] == 195
    assert data["last_hit"]["status_code"] == 200
    assert data["last_hit"]["latency_ms"] >= 0
