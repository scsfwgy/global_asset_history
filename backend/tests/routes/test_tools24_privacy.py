"""Public privacy-policy route for the Tools24 mobile application."""

import json
from pathlib import Path

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize(
    "path",
    ["/platform/tools24/privacy", "/platform/tools24/privacy/"],
)
def test_privacy_policy_route_serves_bilingual_policy(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    html = response.get_data(as_text=True)
    assert '<html lang="en">' in html
    assert "Tools24 Privacy Policy | 隐私政策" in html
    assert 'article[lang="en"] { order: 1; }' in html
    assert 'article[lang="zh-CN"] { order: 3; }' in html
    assert "Tools24 隐私政策" in html
    assert "Tools24 Privacy Policy" in html
    assert "https://www.tools24.uk/platform/tools24/privacy" in html
    assert "相机与图片" in html
    assert "麦克风" in html
    assert "位置" in html
    assert "使用情况访问" in html
    assert "does not upload" in html


def test_vercel_rewrites_privacy_policy_to_flask():
    config_path = Path(__file__).resolve().parents[3] / "vercel.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rewrites = {(item["source"], item["destination"]) for item in config["rewrites"]}

    assert ("/platform/tools24/privacy", "/api/index") in rewrites
    assert ("/platform/tools24/privacy/", "/api/index") in rewrites
