"""Official site and release-management coverage for the Tools24 Android app."""

import json
from pathlib import Path

import pytest

from app import app as flask_app


DOWNLOAD_URL = (
    "https://mateo-oss.oss-cn-shanghai.aliyuncs.com/tools24/release/"
    "toosl24_V1.0.1-e1e8c778_57_20260815164933_official_release.apk"
)
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.maxhall.tools24"


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/platform/tools24", "/platform/tools24/"])
def test_tools24_product_route_is_the_official_download_site(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    html = response.get_data(as_text=True)
    assert "Tools24 Android 工具箱 — 官方网站" in html
    assert DOWNLOAD_URL in html
    assert PLAY_STORE_URL in html
    assert "直接下载 APK" in html
    assert "/api/tools24/download-qr.svg" in html
    assert "__TOOLS24_" not in html
    assert 'rel="sponsored nofollow noopener"' in html
    assert 'href="/platform/tools24/privacy"' in html
    assert "/images/tools24/screenshot-home.png" in html
    assert "/images/tools24/screenshot-all-tools.png" in html
    assert "/images/tools24/screenshot-qr-generator.png" in html
    assert "/images/tools24/screenshot-level.png" in html
    assert "/images/tools24/screenshot-unit-converter.png" in html
    assert "/images/tools24/screenshot-compass.png" not in html
    assert html.count('width="1440" height="3200"') == 6
    assert "aspect-ratio: 9 / 20;" in html


@pytest.mark.parametrize("host", ["tools24.uk", "www.tools24.uk", "www.tools24.uk:8730"])
def test_tools24_domain_home_remains_the_project_directory(client, host):
    response = client.get("/", headers={"Host": host})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "tools24.uk — 实用工具聚合平台" in html
    assert "https://qqq.tools24.uk/" in html
    assert "https://dev.tools24.uk/" in html
    assert 'class="card app-card" href="https://app.tools24.uk/"' in html
    assert "Tools24 Android 工具箱 — 官方网站" not in html


def test_app_tools24_domain_home_is_the_official_app_site(client):
    response = client.get("/", headers={"Host": "app.tools24.uk"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Tools24 Android 工具箱 — 官方网站" in html
    assert "直接下载 APK" in html
    assert DOWNLOAD_URL in html
    assert '<link rel="canonical" href="https://app.tools24.uk/">' in html
    assert "/images/tools24/app-icon.png" in html


def test_app_tools24_domain_allows_local_preview_port(client):
    response = client.get("/", headers={"Host": "app.tools24.uk:8730"})

    assert response.status_code == 200
    assert "Tools24 Android 工具箱 — 官方网站" in response.get_data(as_text=True)


def test_qqq_domain_keeps_the_financial_site(client):
    response = client.get("/", headers={"Host": "qqq.tools24.uk"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Tools24 Android 工具箱 — 官方网站" not in html
    assert "GlobalAssetHistory - 历史涨跌幅与定投回测工具" in html


def test_platform_tools24_still_serves_app_site_from_other_hosts(client):
    response = client.get("/", headers={"Host": "www.tools24.uk"})
    assert "tools24.uk — 实用工具聚合平台" in response.get_data(as_text=True)

    response = client.get("/platform/tools24", headers={"Host": "www.tools24.uk"})
    assert "Tools24 Android 工具箱 — 官方网站" in response.get_data(as_text=True)


def test_tools24_release_api_rejects_missing_token(client, monkeypatch):
    monkeypatch.setenv("WISH_ADMIN_TOKEN", "test-secret")

    response = client.put("/api/tools24/release", json={"download_url": DOWNLOAD_URL})

    assert response.status_code == 403


def test_tools24_release_api_updates_page_and_qr(client, monkeypatch):
    import app as app_module

    state = {
        "download_url": DOWNLOAD_URL,
        "version": "1.0.1",
        "updated_at": None,
        "google_play_url": PLAY_STORE_URL,
    }

    def fake_set(download_url):
        state.update(download_url=download_url, version="1.0.2", updated_at="2026-08-15T10:00:00+00:00")
        return dict(state)

    monkeypatch.setenv("WISH_ADMIN_TOKEN", "test-secret")
    monkeypatch.setattr(app_module, "get_tools24_release", lambda: dict(state))
    monkeypatch.setattr(app_module, "set_tools24_release", fake_set)
    new_url = "https://downloads.example.com/tools24_V1.0.2_official.apk"
    previous_qr = client.get("/api/tools24/download-qr.svg")

    response = client.put(
        "/api/tools24/release",
        headers={"X-Admin-Token": "test-secret"},
        json={"download_url": new_url},
    )

    assert response.status_code == 200
    assert response.get_json()["download_url"] == new_url
    assert new_url in client.get("/platform/tools24").get_data(as_text=True)
    qr_response = client.get("/api/tools24/download-qr.svg")
    assert qr_response.status_code == 200
    assert qr_response.mimetype == "image/svg+xml"
    assert b"<svg" in qr_response.data
    assert qr_response.headers["Cache-Control"].startswith("no-cache")
    assert qr_response.headers["ETag"] != previous_qr.headers["ETag"]
    assert qr_response.data != previous_qr.data


@pytest.mark.parametrize(
    "download_url",
    ["http://example.com/app.apk", "https://example.com/app.zip", "not-a-url"],
)
def test_tools24_release_api_validates_apk_url(client, monkeypatch, download_url):
    monkeypatch.setenv("WISH_ADMIN_TOKEN", "test-secret")

    response = client.put(
        "/api/tools24/release",
        headers={"Authorization": "Bearer test-secret"},
        json={"download_url": download_url},
    )

    assert response.status_code == 400


def test_vercel_rewrites_tools24_product_page_to_flask():
    config_path = Path(__file__).resolve().parents[3] / "vercel.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rewrites = {(item["source"], item["destination"]) for item in config["rewrites"]}

    assert ("/platform/tools24", "/api/index") in rewrites
    assert ("/platform/tools24/", "/api/index") in rewrites
    assert ("/", "/api/index") in rewrites
