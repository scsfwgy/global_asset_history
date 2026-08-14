"""Public product page and landing-card coverage for the Tools24 Android app."""

import json
from pathlib import Path

import pytest

from app import app as flask_app


PLAY_TESTING_URL = "https://play.google.com/apps/testing/com.maxhall.tools24"


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/platform/tools24", "/platform/tools24/"])
def test_tools24_product_route_invites_users_to_google_play_testing(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    html = response.get_data(as_text=True)
    assert "Tools24 Android 工具箱 — 邀请参与内测" in html
    assert PLAY_TESTING_URL in html
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


def test_tools24_landing_home_has_product_card(client):
    response = client.get("/", headers={"Host": "www.tools24.uk"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="card app-card" href="/platform/tools24"' in html
    assert "Tools24 Android" in html
    assert "内测招募中" in html
    assert "/images/tools24/app-icon.png" in html


def test_tools24_landing_host_allows_local_preview_port(client):
    response = client.get("/", headers={"Host": "www.tools24.uk:8730"})

    assert response.status_code == 200
    assert "Tools24 Android" in response.get_data(as_text=True)


def test_vercel_rewrites_tools24_product_page_to_flask():
    config_path = Path(__file__).resolve().parents[3] / "vercel.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rewrites = {(item["source"], item["destination"]) for item in config["rewrites"]}

    assert ("/platform/tools24", "/api/index") in rewrites
    assert ("/platform/tools24/", "/api/index") in rewrites
