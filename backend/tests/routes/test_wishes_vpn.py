"""Tests for admin-only wishes VPN monitor and probe endpoints."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

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


def test_vpn_subscription_requires_admin_token(client):
    resp = client.post("/api/wishes/vpn-subscription", json={"url": "https://example.com/sub.yaml"})
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "ftp://example.com/sub.yaml",
        "http://127.0.0.1/sub.yaml",
        "http://localhost:8080/sub.yaml",
        "http://169.254.169.254/latest/meta-data",
        "https://10.0.0.1/sub.yaml",
    ],
)
def test_vpn_subscription_rejects_invalid_or_internal_urls(client, monkeypatch, bad_url):
    monkeypatch.setenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
    resp = client.post(
        "/api/wishes/vpn-subscription",
        json={"url": bad_url},
        headers={"X-Admin-Token": "test-secret-token"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_select_anti_abuse_proxies_prefers_diverse_regions_and_daily_nodes():
    raw = [
        {"name": "到期: 2027-10-16", "server": "1.2.3.4", "port": 443, "type": "ss"},
        {"name": "流量: 64 GB / 200 GB", "server": "1.2.3.4", "port": 443, "type": "ss"},
        {"name": "🇭🇰 高级 香港 01", "server": "a.example.com", "port": 1001, "type": "anytls"},
        {"name": "🇭🇰 日用 专线 香港[0.2]", "server": "a.example.com", "port": 1002, "type": "anytls"},
        {"name": "🇺🇸 高级 美国 01", "server": "a.example.com", "port": 1003, "type": "anytls"},
        {"name": "🇺🇸 日用 专线 美国[0.2]", "server": "a.example.com", "port": 1004, "type": "anytls"},
        {"name": "🇸🇬 日用 专线 狮城[0.2]", "server": "a.example.com", "port": 1005, "type": "anytls"},
        {"name": "🇯🇵 日用 专线 日本[0.2]", "server": "a.example.com", "port": 1006, "type": "anytls"},
        {"name": "🇹🇼 台湾 01", "server": "a.example.com", "port": 1007, "type": "anytls"},
        {"name": "🇬🇧 英国 01", "server": "a.example.com", "port": 1008, "type": "anytls"},
    ]
    picked = vpn_service._select_anti_abuse_proxies(raw, max_nodes=5)
    assert [p["name"] for p in picked] == [
        "🇺🇸 日用 专线 美国[0.2]",
        "🇸🇬 日用 专线 狮城[0.2]",
        "🇯🇵 日用 专线 日本[0.2]",
        "🇹🇼 台湾 01",
        "🇭🇰 日用 专线 香港[0.2]",
    ]


def test_build_anti_abuse_mihomo_config_emits_lazy_fallback(monkeypatch):
    monkeypatch.setenv("MIHOMO_CONTROLLER_URL", "http://172.17.0.1:9090")
    monkeypatch.setenv("MIHOMO_CONTROLLER_SECRET", "ctrl-sec")
    monkeypatch.setenv("MIHOMO_PROXY_GROUP", "YahooAuto")

    raw_sub = yaml.safe_dump(
        {
            "proxies": [
                {"name": "到期: 2027-01-01", "server": "1.1.1.1", "port": 443, "type": "ss"},
                {"name": "🇺🇸 US 01", "server": "us.example.com", "port": 443, "type": "trojan"},
                {"name": "🇯🇵 JP 01", "server": "jp.example.com", "port": 443, "type": "trojan"},
            ]
        },
        allow_unicode=True,
    )
    yaml_text, selected_names, total_count = vpn_service.build_anti_abuse_mihomo_config(raw_sub)
    assert total_count == 2
    assert selected_names == ["🇺🇸 US 01", "🇯🇵 JP 01"]
    cfg = yaml.safe_load(yaml_text)
    assert cfg["secret"] == "ctrl-sec"
    assert cfg["lan-allowed-ips"] == ["127.0.0.1/8", "172.17.0.0/16"]
    group = cfg["proxy-groups"][0]
    assert group["type"] == "fallback"
    assert group["lazy"] is True
    assert group["interval"] == 1800
    assert group["expected-status"] == 200


def test_vpn_subscription_updates_file_and_reloads_mihomo(client, monkeypatch, tmp_path):
    cfg_file = tmp_path / ".mihomo-config.yaml"
    monkeypatch.setenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("MIHOMO_CONTROLLER_SECRET", "ctrl-sec")
    monkeypatch.setenv("MIHOMO_CONFIG_PATH", str(cfg_file))
    monkeypatch.setenv("MIHOMO_HOST_CONFIG_PATH", "/srv/host/.mihomo-config.yaml")

    with vpn_service._last_hit_lock:
        vpn_service._last_hit = {"node": "OldNode"}

    raw_sub = yaml.safe_dump(
        {
            "proxies": [
                {"name": "🇺🇸 US 01", "server": "us.example.com", "port": 443, "type": "trojan"},
                {"name": "🇯🇵 JP 01", "server": "jp.example.com", "port": 443, "type": "trojan"},
            ]
        },
        allow_unicode=True,
    ).encode("utf-8")

    sub_resp = MagicMock()
    sub_resp.raise_for_status = MagicMock()
    sub_resp.iter_content.return_value = [raw_sub]

    proxies_resp = MagicMock()
    proxies_resp.raise_for_status = MagicMock()
    proxies_resp.json.return_value = {
        "proxies": {
            "YahooAuto": {"type": "Fallback", "now": "🇺🇸 US 01", "all": ["🇺🇸 US 01", "🇯🇵 JP 01"]},
            "🇺🇸 US 01": {"type": "Trojan", "alive": True, "history": [{"delay": 150}]},
            "🇯🇵 JP 01": {"type": "Trojan", "alive": True, "history": [{"delay": 180}]},
        }
    }

    conns_resp = MagicMock()
    conns_resp.raise_for_status = MagicMock()
    conns_resp.json.return_value = {"uploadTotal": 0, "downloadTotal": 0, "connections": []}

    put_resp = MagicMock()
    put_resp.raise_for_status = MagicMock()

    def fake_get(url, **kwargs):
        if url.startswith("https://sub.example.com"):
            return sub_resp
        if url.endswith("/proxies"):
            return proxies_resp
        return conns_resp

    with patch.object(vpn_service._ctrl_session, "get", side_effect=fake_get), \
         patch.object(vpn_service._ctrl_session, "put", return_value=put_resp) as mock_put, \
         patch("service.wishes.vpn_service.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        resp = client.post(
            "/api/wishes/vpn-subscription",
            json={"url": "https://sub.example.com/clash.yaml"},
            headers={"X-Admin-Token": "test-secret-token"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["last_hit"] is None
    assert data["subscription_update"]["mode"] == "anti_abuse"
    assert data["subscription_update"]["selected_count"] == 2
    assert cfg_file.exists()
    assert (cfg_file.stat().st_mode & 0o777) == 0o600
    mock_put.assert_called_once()
    assert mock_put.call_args.kwargs["json"] == {"path": "/srv/host/.mihomo-config.yaml"}
